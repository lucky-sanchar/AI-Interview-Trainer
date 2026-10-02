import json
import requests
import re
import warnings
import logging
import subprocess
import sys
import tempfile
import os
import difflib
from google import genai

# =========================================================
# 1. API KEYS SETUP (Coding Evaluation Pools)
from config import CODE_GROQ_KEYS, CODE_GEMINI_KEYS, CODE_COHERE_KEYS
# =========================================================

warnings.filterwarnings("ignore")
logging.getLogger("google").setLevel(logging.ERROR)

MIN_CODE_LENGTH = 15
VALID_STATUSES = {"Correct", "Partial", "Wrong", "Incomplete"}


def parse_json_response(ai_text):
    try:
        match = re.search(r'\{.*\}', ai_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(ai_text)
    except Exception as e:
        print(f"  ⚠️ [X-RAY ERROR] JSON Parsing Failed. Raw text: {str(ai_text)[:60]}...")
        return None


def _valid_ai_result(parsed):
    """⚡ X-RAY: Validates the AI's status so that 'correct' (lowercase) or some
    random string doesn't silently give 0 marks while the UI shows 'wrong'."""
    if not parsed or "status" not in parsed:
        return False
    if parsed["status"] not in VALID_STATUSES:
        print(f"  ⚠️ [X-RAY] AI returned an invalid status: '{parsed['status']}'. Rejecting it.")
        return False
    return True


# =========================================================
# LANGUAGE CHECK
# =========================================================
NON_PYTHON_WORDS = {
    "node", "nodejs", "javascript", "js", "java", "c++", "cpp", "c#", "csharp",
    "ruby", "go", "golang", "php", "dax", "sql", "mysql", "postgres", "postgresql",
    "mongodb", "bash", "shell", "git", "html", "css", "react", "excel", "aws",
    "docker", "kubernetes", "linux"
}

def is_python_category(category):
    cat_lower = str(category).lower()
    if "power bi" in cat_lower:
        print(f"🔍 [X-RAY] Category '{category}' -> Power BI detected, treating as non-Python.")
        return False
    tokens = set(re.findall(r'[a-z0-9+#]+', cat_lower))
    result = not (tokens & NON_PYTHON_WORDS)
    print(f"🔍 [X-RAY] Category '{category}' -> is_python_category = {result}")
    return result

# =========================================================
# LAYER 1: SECURITY
# =========================================================
DANGEROUS_PATTERNS = [
    r'\bos\.system\b', r'\bos\.remove\b', r'\bos\.unlink\b', r'\bos\.rmdir\b',
    r'\bshutil\.rmtree\b', r'\bsubprocess\b', r'\b__import__\b',
    r'\beval\s*\(', r'\bexec\s*\(', r'\bopen\s*\([^)]*[\'"]w',
    r'\bsocket\b', r'\brequests\b', r'\burllib\b', r'\bctypes\b',
    r'\bos\.fork\b', r'\bos\.kill\b', r'\bsys\.exit\b',
]

def security_scan(user_code):
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, user_code):
            msg = f"🚨 Security Block: This code uses a restricted operation ({pattern}). File/system access is not allowed."
            print(f"🛡️ [SECURITY-X-RAY] ❌ BLOCKED — pattern matched: {pattern}")
            return False, msg
    print("🛡️ [SECURITY-X-RAY] ✅ Code is safe, no dangerous pattern found.")
    return True, "Basic Safety Check Passed"

# =========================================================
# LOCAL PYTHON EXECUTION
# =========================================================
def run_python_locally(code, stdin_data, timeout=6):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name

        result = subprocess.run(
            [sys.executable, temp_path],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        print("⏱️ [EXEC-X-RAY] ❌ Timeout — possible infinite loop or very slow code.")
        return -1, "", "Execution timed out (possible infinite loop or very slow code)."
    except Exception as e:
        print(f"⏱️ [EXEC-X-RAY] ❌ Execution crash: {e}")
        return -1, "", f"Execution failed: {str(e)}"
    finally:
        if temp_path and os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass

# =========================================================
# OUTPUT NORMALIZER
# =========================================================
def _to_text(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "\n".join(_to_text(v) for v in value)
    return str(value)

def normalize_output(text):
    text = _to_text(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.strip().split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)

# =========================================================
# LAYER 2: LOCAL EXECUTION + TEST CASE CHECKING
# =========================================================
def run_test_cases(user_code, test_cases, category="Python"):
    if not is_python_category(category):
        print(f"⚙️ [LAYER 2] Local execution is not supported for '{category}' — AI will review it instead.")
        return True, 0, 0, f"⚠️ The local sandbox only supports Python. '{category}' logic will be reviewed by AI (no I/O tests will run)."

    valid_cases = []
    for tc in (test_cases or []):
        if isinstance(tc, dict):
            inp = tc.get("input", tc.get("stdin", ""))
            out = tc.get("output", tc.get("expected_output", tc.get("expected", "")))
        elif isinstance(tc, (list, tuple)) and len(tc) == 2:
            inp, out = tc
        else:
            print(f"⚙️ [LAYER 2] ⚠️ One test case had an unrecognized format, skipping: {tc}")
            continue
        valid_cases.append((inp, out))

    total_cases = len(valid_cases)
    print(f"⚙️ [LAYER 2] Total usable test cases: {total_cases}")

    if total_cases == 0:
        print("⚙️ [LAYER 2] ⚠️ No valid test cases found — only a manual AI review will happen.")
        return True, 0, 0, "No direct I/O test cases. Logic will be evaluated by AI."

    print("⚙️ [LAYER 2] Running Python Code locally (subprocess sandbox)...")
    passed_cases = 0

    for i, (test_input, expected_output) in enumerate(valid_cases):
        stdin_data = _to_text(test_input)
        if not stdin_data.endswith("\n"):
            stdin_data += "\n"

        return_code, actual_output, stderr = run_python_locally(user_code, stdin_data)
        print(f"⚙️ [LAYER 2] Test {i+1}/{total_cases}: return_code={return_code}")

        if return_code != 0:
            error_msg = stderr if stderr else actual_output
            print(f"⚙️ [LAYER 2] ❌ Test {i+1} crashed: {error_msg[:100]}")
            return False, passed_cases, total_cases, f"Error on Test {i+1}:\n{error_msg}"

        if normalize_output(actual_output) == normalize_output(expected_output):
            print(f"⚙️ [LAYER 2] ✅ Test {i+1} PASSED.")
            passed_cases += 1
        else:
            print(f"⚙️ [LAYER 2] ❌ Test {i+1} FAILED. Expected='{expected_output}' Got='{actual_output.strip()}'")
            return False, passed_cases, total_cases, (
                f"Failed on Test {i+1}.\n"
                f"Expected: '{normalize_output(expected_output)}'\n"
                f"Got: '{normalize_output(actual_output)}'"
            )

    print(f"⚙️ [LAYER 2] ✅ All {total_cases} test cases PASSED.")
    return True, passed_cases, total_cases, "All test cases passed successfully! ✅"

# =========================================================
# LAYER 3: AI CODE REVIEW
# =========================================================
def ai_code_review(question, user_code, is_passed, exec_message, difficulty, category, total_cases=0, passed_cases=0):
    if is_passed and total_cases > 0:
        ai_instruction = f"The code PASSED all {total_cases} automated test cases ({passed_cases}/{total_cases}). Give a warm, encouraging congratulation, provide Time/Space Complexity, and gently suggest a pro-tip for optimization if any."
        status_rule = 'Set "status" to "Correct" — it is verified, automated tests actually passed.'
    elif is_passed and total_cases == 0:
        ai_instruction = (
            f"No automated test cases could be executed for this '{category}' category "
            f"(reason: '{exec_message}'). This does NOT mean the code is correct — nothing has been verified yet. "
            "Carefully read the candidate's code line by line, mentally trace through the logic, and judge whether "
            "it genuinely and completely solves the question, including edge cases."
        )
        status_rule = (
            'Decide "status" YOURSELF purely from your manual reading — do NOT default to "Correct". '
            'Use "Correct" only if the logic is genuinely sound and complete. Use "Partial" if the approach is right '
            'but has bugs or gaps. Use "Wrong" if the code is broken, irrelevant, or does not attempt the problem.'
        )
    else:
        ai_instruction = f"The execution engine reported: '{exec_message}'. Be supportive. Point out the issue gently."
        status_rule = 'Set "status" to "Partial" if the approach is right but has a bug, or "Wrong" if it is fundamentally incorrect or has a syntax/runtime error.'

    print(f"🤖 [AI-REVIEW-X-RAY] Mode: is_passed={is_passed}, total_cases={total_cases}, passed_cases={passed_cases}")

    prompt = f"""
    You are an empathetic, supportive Senior {category} Developer reviewing a junior's code.
    Candidate Level: {difficulty}
    Question: {question}
    Candidate's Code: {user_code}
    Result Instruction: {ai_instruction}
    Status Instruction: {status_rule}
    
    Return EXACTLY this JSON structure: {{"status": "Correct" | "Partial" | "Wrong", "complexity": "O(N)...", "feedback": "Your warm, helpful hint here."}}
    """

    print(" 🟢 [ENGINE 1] Routing to Groq for Code Review...")
    for index, key in enumerate(CODE_GROQ_KEYS):
        if not key or key.startswith("YOUR_"):
            continue
        try:
            print(f"  -> Testing Groq Key {index + 1}...")
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "response_format": {"type": "json_object"}, "max_tokens": 2048},
                timeout=8.0
            )
            res.raise_for_status()
            parsed = parse_json_response(res.json()["choices"][0]["message"]["content"])
            if _valid_ai_result(parsed):
                print(f" 🟢 [ENGINE 1] SUCCESS (Groq Key {index + 1}) -> Status: {parsed['status']}")
                return parsed
            else:
                print(f"  ⚠️ [X-RAY] Groq Key {index + 1} did not return usable JSON.")
        except Exception as e:
            print(f"  ⚠️ [EVALUATION ERROR] Groq Key {index+1} Failed: {e}")

    print(" 🔵 [ENGINE 2] Routing to Gemini for Code Review...")
    for index, key in enumerate(CODE_GEMINI_KEYS):
        if not key or key.startswith("YOUR_"):
            continue
        try:
            print(f"  -> Testing Gemini Key {index + 1}...")
            client = genai.Client(api_key=key)
            parsed = parse_json_response(client.models.generate_content(model='gemini-3.5-flash', contents=prompt).text)
            if _valid_ai_result(parsed):
                print(f" 🔵 [ENGINE 2] SUCCESS (Gemini Key {index + 1}) -> Status: {parsed['status']}")
                return parsed
            else:
                print(f"  ⚠️ [X-RAY] Gemini Key {index + 1} did not return usable JSON.")
        except Exception as e:
            print(f"  ⚠️ [EVALUATION ERROR] Gemini Key {index+1} Failed: {e}")

    print(" 🟣 [ENGINE 3] Routing to Cohere for Code Review...")
    if CODE_COHERE_KEYS and not CODE_COHERE_KEYS.startswith("YOUR_"):
        try:
            headers = {"Authorization": f"Bearer {CODE_COHERE_KEYS}", "Content-Type": "application/json"}
            payload = {"model": "command-r7b-12-2024", "message": prompt, "temperature": 0.1, "max_tokens": 2048}
            res = requests.post("https://api.cohere.com/v1/chat", headers=headers, json=payload, timeout=8.0)
            res.raise_for_status()
            parsed = parse_json_response(res.json()["text"])
            if _valid_ai_result(parsed):
                print(f" 🟣 [ENGINE 3] SUCCESS (Cohere) -> Status: {parsed['status']}")
                return parsed
            else:
                print("  ⚠️ [X-RAY] Cohere did not return usable JSON.")
        except Exception as e:
            print(f"⚠️ [EVALUATION ERROR] Cohere Failed: {e}")
    else:
        print("  ⚠️ [X-RAY] Cohere key is not set or is a placeholder, skipping.")

    print("🚨 [CRITICAL] All AI Evaluation Engines Failed! Falling back to static mode.")
    return None

# =========================================================
# THE SMART FALLBACK: only runs when the AI crashes
# =========================================================
def static_code_fallback(is_passed, exec_message, total_cases, passed_cases, user_code, ideal_answer, keywords):
    print(f"🧯 [STATIC-FALLBACK-X-RAY] Activated. total_cases={total_cases}, is_passed={is_passed}")

    # 1. Python Code (Verified by Sandbox)
    if total_cases > 0:
        if is_passed:
            print("🧯 [STATIC-FALLBACK-X-RAY] Verified by the sandbox -> Correct.")
            return {"status": "Correct", "complexity": "Offline Mode", "feedback": f"All {passed_cases}/{total_cases} test cases passed! ✅ (Verified Offline)"}
        else:
            print("🧯 [STATIC-FALLBACK-X-RAY] Verified by the sandbox -> Wrong.")
            return {"status": "Wrong", "complexity": "N/A", "feedback": f"Code failed on local execution. {exec_message} ❌"}

    # 2. Non-Python Code (Sandbox didn't run, AI crashed) -> Use DB Reference
    else:
        if not ideal_answer and not keywords:
            print("🧯 [STATIC-FALLBACK-X-RAY] ❌ No ideal answer/keywords available either — manual review is required.")
            return {"status": "Incomplete", "complexity": "N/A", "feedback": "⚠️ AI service is down. Manual review required."}

        user_code_lower = str(user_code).lower()
        keyword_list = [k.strip().lower() for k in keywords.split(",")] if keywords else []

        keys_found = sum(1 for k in keyword_list if k in user_code_lower)
        key_score = (keys_found / len(keyword_list)) if keyword_list else 0

        similarity = difflib.SequenceMatcher(None, user_code_lower, str(ideal_answer).lower()).ratio()
        print(f"🧯 [STATIC-FALLBACK-X-RAY] similarity={similarity*100:.1f}%, keyword_score={key_score*100:.1f}% ({keys_found}/{len(keyword_list)})")

        if similarity > 0.5 or key_score >= 0.6:
            status = "Correct"
        elif similarity > 0.25 or key_score >= 0.3:
            status = "Partial"
        else:
            status = "Wrong"
        print(f"🧯 [STATIC-FALLBACK-X-RAY] Final verdict -> {status}")

        if status == "Correct":
            return {"status": "Correct", "complexity": "Offline", "feedback": "⚠️ AI down, but code logic/keywords match expected approach! ✅"}
        elif status == "Partial":
            return {"status": "Partial", "complexity": "Offline", "feedback": "⚠️ AI down. Code has some correct elements but might be incomplete. 🟨"}
        else:
            return {"status": "Wrong", "complexity": "N/A", "feedback": "⚠️ AI down. Code does not match expected logic or mandatory keywords. ❌"}

# =========================================================
# MAIN EVALUATOR
# =========================================================
def evaluate_candidate_code(question, user_code, test_cases, ideal_answer, keywords, difficulty="Applied", category="Python"):
    print("\n" + "="*50)
    print("💻 EVALUATING CANDIDATE CODE")
    print(f"🔍 [X-RAY] Category: {category} | Difficulty: {difficulty} | Test cases available: {len(test_cases or [])}")
    print("="*50)

    cleaned_code = (user_code or "").strip()

    # ⚡ X-RAY NOTE: This returns "Wrong" (-0.25) for very short code, whereas
    # evaluate_answer.py returns "Incomplete" (0) for theory answers. This is an
    # intentional difference (a code answer should contain at least some valid
    # code) — if you want them consistent, you can change this to "Incomplete" too.
    if len(cleaned_code) < MIN_CODE_LENGTH:
        print(f"❌ [X-RAY] Code is too short (< {MIN_CODE_LENGTH} chars). Marking straight as Wrong.")
        return {"status": "Wrong", "complexity": "N/A", "feedback": "❌ The answer is too short or empty. Please write valid code/logic."}

    is_safe, sec_msg = security_scan(cleaned_code)
    if not is_safe:
        print("❌ [X-RAY] Security scan failed — won't proceed to AI/sandbox at all.")
        return {"status": "Wrong", "complexity": "N/A", "feedback": sec_msg}

    is_passed, passed_cases, total_cases, exec_message = run_test_cases(cleaned_code, test_cases, category)
    print(f"📊 [X-RAY] Sandbox result -> passed={is_passed}, {passed_cases}/{total_cases}")

    ai_result = ai_code_review(question, cleaned_code, is_passed, exec_message, difficulty, category, total_cases, passed_cases)

    if ai_result:
        print(f"✅ [X-RAY] Final result came from AI -> Status: {ai_result.get('status')}")
        return ai_result

    print("⚠️ [X-RAY] No result from AI, using static_code_fallback.")
    fallback_result = static_code_fallback(is_passed, exec_message, total_cases, passed_cases, cleaned_code, ideal_answer, keywords)
    print(f"✅ [X-RAY] Final result came from fallback -> Status: {fallback_result.get('status')}")
    return fallback_result

def calculate_code_score(evaluation_result):
    status = evaluation_result.get("status", "Incomplete")
    print(f"🧮 [SCORE-X-RAY] Calculating code score for status='{status}'...")
    if status == "Correct":
        return 1.0
    elif status == "Partial":
        return 0.5
    elif status == "Wrong":
        return -0.25
    return 0.0

if __name__ == "__main__":
    print("\n🚀 STARTING HARDCODED TEST SUITE FOR code_evaluate.py...")

    # Hardcoded Question & Test Cases for Python
    hc_py_question = (
        "Problem Statement: Write a Python program that reads a single line of space-separated integers "
        "from standard input and prints the sum of all even numbers."
    )
    hc_py_test_cases = [
        ["1 2 3 4 5 6", "12"],
        ["10 15 20", "30"],
        ["1 3 5", "0"]
    ]
    hc_py_ideal = "nums = list(map(int, input().split()))\nprint(sum(x for x in nums if x % 2 == 0))"
    hc_py_keywords = "input, split, map, int, sum"

    # --- TEST 1: Correct Python Code (Should Pass Sandbox 3/3 + Get AI 'Correct') ---
    print("\n--- TEST 1: Correct Python Submission (Sandbox + AI) ---")
    valid_py_code = """
data = list(map(int, input().split()))
even_sum = sum(n for n in data if n % 2 == 0)
print(even_sum)
"""
    res1 = evaluate_candidate_code(
        question=hc_py_question,
        user_code=valid_py_code,
        test_cases=hc_py_test_cases,
        ideal_answer=hc_py_ideal,
        keywords=hc_py_keywords,
        difficulty="Foundation",
        category="Python"
    )
    print(json.dumps(res1, indent=2))
    print(f"Points: {calculate_code_score(res1)}")

    # --- TEST 2: Broken Python Code (Should Fail Sandbox + Get AI 'Wrong'/'Partial') ---
    print("\n--- TEST 2: Incorrect Python Logic (Fails Sandbox) ---")
    wrong_py_code = """
data = list(map(int, input().split()))
# Bug: summing all numbers instead of only even numbers
print(sum(data))
"""
    res2 = evaluate_candidate_code(
        question=hc_py_question,
        user_code=wrong_py_code,
        test_cases=hc_py_test_cases,
        ideal_answer=hc_py_ideal,
        keywords=hc_py_keywords,
        difficulty="Foundation",
        category="Python"
    )
    print(json.dumps(res2, indent=2))
    print(f"Points: {calculate_code_score(res2)}")

    # --- TEST 3: Non-Python Code (JavaScript - Skips Sandbox, AI Reviews Directly) ---
    print("\n--- TEST 3: Non-Python Submission (JavaScript - AI Logic Review) ---")
    hc_js_question = "Write a JavaScript function `reverseString(str)` that returns the reversed string."
    valid_js_code = """
function reverseString(str) {
    return str.split('').reverse().join('');
}
"""
    res3 = evaluate_candidate_code(
        question=hc_js_question,
        user_code=valid_js_code,
        test_cases=[],
        ideal_answer="function reverseString(s) { return s.split('').reverse().join(''); }",
        keywords="function, split, reverse, join, return",
        difficulty="Foundation",
        category="JavaScript"
    )
    print(json.dumps(res3, indent=2))
    print(f"Points: {calculate_code_score(res3)}")

    # --- TEST 4: Short / Invalid Input (Should be caught by Pre-Check without API call) ---
    print("\n--- TEST 4: Invalid / Brief Input (Local Pre-Check) ---")
    short_input = "idk bro"
    res4 = evaluate_candidate_code(
        question=hc_py_question,
        user_code=short_input,
        test_cases=hc_py_test_cases,
        ideal_answer=hc_py_ideal,
        keywords=hc_py_keywords,
        difficulty="Foundation",
        category="Python"
    )
    print(json.dumps(res4, indent=2))
    print(f"Points: {calculate_code_score(res4)}")