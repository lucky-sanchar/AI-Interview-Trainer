import sqlite3
import socket
import requests
from google import genai
import random
import difflib
import warnings
import logging
import json
import re
from roles_db import ROLES_DATA 

# =========================================================
# 1. API KEYS SETUP (loaded from config.py / .env file)
from config import GEN_GROQ_KEYS, GEN_GEMINI_KEYS, GEN_COHERE_KEY
# =========================================================

warnings.filterwarnings("ignore")
logging.getLogger("google").setLevel(logging.ERROR)

# =========================================================
# 0. TEST-CASE VALIDATOR (X-RAY: catches wrong expected-output values from the AI)
# =========================================================
try:
    from code_evaluate import run_python_locally, normalize_output, _to_text, security_scan
    _CODE_EVAL_AVAILABLE = True
except Exception as e:
    print(f"⚠️ [X-RAY] Failed to import code_evaluate, test-case validation will be SKIPPED: {e}")
    _CODE_EVAL_AVAILABLE = False

def validate_test_cases(ideal_answer, test_cases):
    """
    Runs the AI's own 'ideal_answer' (its own 'correct' code) against each test case's
    stdin, and compares the real output with the 'expected output' the AI provided.
    Only test cases that are genuinely correct are returned — the rest are dropped.
    """
    print(f"🧪 [X-RAY | VALIDATE] Starting validation... Received {len(test_cases or [])} test cases from AI.")

    if not _CODE_EVAL_AVAILABLE:
        print("🧪 [X-RAY | VALIDATE] code_evaluate not available, keeping all test cases as-is.")
        return test_cases or []

    code = re.sub(r"^```(?:python)?\s*|\s*```$", "", str(ideal_answer or "").strip())
    if not code:
        print("🧪 [X-RAY | VALIDATE] ❌ ideal_answer is empty — no test case can be validated. Dropping all.")
        return []

    is_safe, sec_msg = security_scan(code)
    if not is_safe:
        print(f"🧪 [X-RAY | VALIDATE] 🚨 ideal_answer failed the security scan: {sec_msg}. Dropping all test cases.")
        return []

    good = []
    for i, tc in enumerate(test_cases or []):
        if isinstance(tc, dict):
            inp = tc.get("input", tc.get("stdin", ""))
            out = tc.get("output", tc.get("expected_output", tc.get("expected", "")))
        elif isinstance(tc, (list, tuple)) and len(tc) == 2:
            inp, out = tc
        else:
            print(f"🧪 [X-RAY | VALIDATE] Test {i+1}: ❌ unrecognized format, skipping.")
            continue

        stdin_data = _to_text(inp)
        if not stdin_data.endswith("\n"):
            stdin_data += "\n"

        rc, actual, err = run_python_locally(code, stdin_data)

        if rc != 0:
            print(f"🧪 [X-RAY | VALIDATE] Test {i+1}: ❌ ideal_answer itself crashed -> {err[:80]}")
            continue

        if normalize_output(actual) == normalize_output(out):
            print(f"🧪 [X-RAY | VALIDATE] Test {i+1}: ✅ VALID (expected='{out}', got='{actual.strip()}')")
            good.append([_to_text(inp), _to_text(out)])
        else:
            print(f"🧪 [X-RAY | VALIDATE] Test {i+1}: ❌ REJECTED — AI's expected output was wrong! "
                  f"(AI said='{out}', actual output='{actual.strip()}')")

    print(f"🧪 [X-RAY | VALIDATE] Final result: {len(good)}/{len(test_cases or [])} test cases verified-safe.")
    return good

# =========================================================
# 2. SMART JSON CLEANER (extracts JSON from the AI's raw output)
# =========================================================
def parse_json_response(ai_text):
    try:
        match = re.search(r'\{.*\}', ai_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(ai_text)
    except Exception as e:
        print(f"  ⚠️ JSON Parsing Error: Raw text: {ai_text[:50]}...")
        return None

# =========================================================
# 3. X-RAY DUPLICATE CHECKER
# =========================================================
def is_duplicate(new_q, seen_list):
    if not seen_list:
        return False, 0.0

    max_sim = 0.0
    matched_q = ""
    for old_q in seen_list:
        similarity = difflib.SequenceMatcher(None, new_q.lower(), old_q.lower()).ratio()
        if similarity > max_sim:
            max_sim = similarity
            matched_q = old_q

    print(f"   [X-RAY CHECK] Top Match: {max_sim*100:.1f}% with -> '{matched_q[:40]}...'")

    if max_sim > 0.75:
        print(f"   🚨 [REJECTED] Question is {max_sim*100:.1f}% similar to an old one!")
        return True, max_sim
    else:
        print(f"   ✅ [PASSED] Question is UNIQUE (Max similarity: {max_sim*100:.1f}%)")
        return False, max_sim

# =========================================================
# 4. DATABASE INITIALIZATION (Separate DBs for Theory & Coding)
# =========================================================
DB_THEORY = "theory_questions.db"
DB_CODING = "coding_questions.db"

def init_dbs():
    for db in [DB_THEORY, DB_CODING]:
        conn = sqlite3.connect(db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interview_questions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                difficulty TEXT,
                interview_type TEXT, 
                job_role TEXT DEFAULT '',
                question TEXT UNIQUE,
                ideal_answer TEXT,
                mandatory_keywords TEXT,
                test_cases TEXT
            )
        """)
        # Safe migration — add the job_role column to older DB files if it's missing
        try:
            conn.execute("ALTER TABLE interview_questions ADD COLUMN job_role TEXT DEFAULT ''")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists, nothing to do
        conn.commit()
        conn.close()

init_dbs()

# =========================================================
# 5. SAVE QUESTION TO DATABASE (Targeted saving + validated test cases)
# =========================================================
def save_question_to_db(category, difficulty, interview_type, question, ideal_answer, keywords, test_cases="[]", job_role=""):
    target_db = DB_CODING if interview_type == "Coding" else DB_THEORY
    try:
        conn = sqlite3.connect(target_db)
        cursor = conn.cursor()

        # Check for duplicates only within the same category
        cursor.execute("SELECT question FROM interview_questions WHERE category=?", (category,))
        existing_questions = [row[0] for row in cursor.fetchall()]

        for old_q in existing_questions:
            similarity = difflib.SequenceMatcher(None, question.lower(), old_q.lower()).ratio()
            if similarity > 0.85:
                print(f" 🗄️ [DB-X-RAY] Duplicate in {target_db}! Match: {similarity*100:.1f}%. Not saving.")
                conn.close()
                return

        # ⚡ FIX (this was the real gap): Before saving Coding question test cases,
        # verify them against the ideal_answer so the AI's wrong expected-output values
        # never make it into the DB.
        if interview_type == "Coding":
            try:
                raw_cases = json.loads(test_cases) if test_cases else []
            except Exception as e:
                print(f" 🧪 [DB-X-RAY] test_cases JSON parse failed: {e}. Using an empty list instead.")
                raw_cases = []
            validated = validate_test_cases(ideal_answer, raw_cases)
            test_cases = json.dumps(validated)
            print(f" 🗄️ [DB-X-RAY] Test cases for this question: {len(raw_cases)} generated -> {len(validated)} verified & saved.")

        cursor.execute(
            "INSERT INTO interview_questions (category, difficulty, interview_type, job_role, question, ideal_answer, mandatory_keywords, test_cases) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (category, difficulty, interview_type, job_role, question, ideal_answer, keywords, test_cases)
        )
        conn.commit()
        conn.close()
        print(f" 🗄️ [DB-X-RAY] ✅ New AI question stored in {target_db}! (Role: {job_role})")
    except sqlite3.IntegrityError:
        print(" 🗄️ [DB-X-RAY] Exact duplicate found in DB. Skipped.")
    except Exception as e:
        print(f"⚠️ DB Save Error: {e}")

# =========================================================
# 6. DATABASE FALLBACK (Targeted fetching)
# =========================================================
def get_fallback_question(category, difficulty, seen_list, interview_type, job_role=""):
    target_db = DB_CODING if interview_type == "Coding" else DB_THEORY
    try:
        conn = sqlite3.connect(target_db)
        cursor = conn.cursor()

        print(f" 🗄️ [DB-X-RAY] Searching {target_db} for Category: '{category}', Diff: '{difficulty}', Role: '{job_role}'")

        base_conditions = ["category=?", "difficulty=?"]
        params = [category, difficulty]

        if job_role:
            base_conditions.append("job_role=?")
            params.append(job_role)

        if seen_list:
            placeholders = ",".join("?" for _ in seen_list)
            base_conditions.append(f"question NOT IN ({placeholders})")
            params += seen_list

        query = f"SELECT question FROM interview_questions WHERE {' AND '.join(base_conditions)} ORDER BY RANDOM() LIMIT 1"
        cursor.execute(query, params)
        row = cursor.fetchone()

        # If no role-specific match was found, try older (role-less / legacy) rows too,
        # so entries from before the role migration are still usable.
        if not row and job_role:
            fallback_conditions = ["category=?", "difficulty=?", "(job_role='' OR job_role IS NULL)"]
            fallback_params = [category, difficulty]
            if seen_list:
                placeholders = ",".join("?" for _ in seen_list)
                fallback_conditions.append(f"question NOT IN ({placeholders})")
                fallback_params += seen_list
            fallback_query = f"SELECT question FROM interview_questions WHERE {' AND '.join(fallback_conditions)} ORDER BY RANDOM() LIMIT 1"
            cursor.execute(fallback_query, fallback_params)
            row = cursor.fetchone()

        conn.close()

        if row:
            print(" 🗄️ [DB-X-RAY] ✅ Found a unique question in the DB!")
            return row[0]
        else:
            print(" 🗄️ [DB-X-RAY] ❌ No new question found in the DB for this criteria.")
            return None
    except Exception as e:
        print(f"⚠️ Database Fetch Error: {e}")
        return None

def check_internet():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2.0)
        return True
    except OSError:
        return False

# =========================================================
# 8. SEPARATE PROMPT GENERATORS (100% Isolated)
# =========================================================
def get_difficulty_guide(difficulty):
    if difficulty == "Foundation":
        return "LEVEL: FOUNDATION. Keep the problem statement EXTREMELY short and direct (1-2 lines). Test pure basic fundamentals and simple logic. NO long stories, NO complex scenarios."
    elif difficulty == "Applied":
        return "LEVEL: APPLIED. Standard interview difficulty. Use a brief, practical scenario. Test standard algorithms or intermediate concepts. Keep it concise."
    elif difficulty == "Advanced":
        return "LEVEL: ADVANCED. Complex problem. Test multiple concepts, edge cases, and optimization. You can use a detailed scenario."
    else: 
        return "LEVEL: EXPERT. Highly complex FAANG-level problem. Focus on deep architectural tradeoffs, extreme optimization, or deep system internals."

def generate_theory_prompt(category, difficulty, avoid_text, attempt, random_seed, job_role):
    diff_guide = get_difficulty_guide(difficulty)
    return f"""
    [System Note: Internal Variation ID {random_seed} - Attempt {attempt+1}]
    ROLE: You are an elite FAANG Senior Technical Interviewer hiring for a '{job_role}' position. 
    Your ONLY goal is to evaluate their '{category}' skills applied to a real-world '{job_role}' scenario.

    {diff_guide}

    CRITICAL RULES:
    1. ROLE CONTEXT: The question MUST be strictly related to the '{job_role}' domain.
    2. DO NOT generate questions similar to these: {avoid_text}
    3. The question must match the requested difficulty. DO NOT ask the candidate to write code.
    4. Return EXACTLY as a valid JSON object. No markdown.

    JSON Format Required:
    {{
        "question": "Your interview question here...",
        "ideal_answer": "A concise perfect technical answer.",
        "mandatory_keywords": "keyword1, keyword2",
        "test_cases": []
    }}
    """

_NON_PYTHON_WORDS = {"node", "nodejs", "javascript", "js", "java", "c++", "cpp", "c#",
                     "csharp", "ruby", "go", "golang", "php", "power bi", "dax", "sql", 
                     "mysql", "postgres", "mongodb", "bash", "shell", "git", "html", 
                     "css", "react", "excel", "aws", "docker", "kubernetes", "linux"}

def _is_python_category(category):
    tokens = set(re.findall(r'[a-z0-9+#]+', str(category).lower()))
    return not (tokens & _NON_PYTHON_WORDS)

def generate_coding_prompt(category, difficulty, avoid_text, attempt, random_seed, job_role):
    diff_guide = get_difficulty_guide(difficulty)

    if _is_python_category(category):
        test_case_rule = (
            "5. TEST CASES: Provide exactly 3 test cases. Each test case is a JSON array of exactly two STRINGS: "
            "[stdin_text, expected_stdout_text]. Multiple input lines are joined with \\n inside ONE string. "
            "Expected output must be a plain string exactly as print() would output it (NOT a list, NOT an array). "
            "The program must read via input() and print() only (no files, no network, no packages)."
        )
    else:
        test_case_rule = (
            "5. TEST CASES: This category cannot be auto-executed by our local sandbox (Python-only). "
            "Always return \"test_cases\": [] — do not attempt to generate I/O test cases."
        )

    return f"""
    [System Note: Internal Variation ID {random_seed} - Attempt {attempt+1}]
    ROLE: You are an elite FAANG Senior Technical Interviewer hiring for a '{job_role}' position. 
    Your ONLY goal is to evaluate their '{category}' skills applied to a real-world '{job_role}' scenario.

    {diff_guide}

    ABSOLUTE CRITICAL RULES (VIOLATION CAUSES SYSTEM FAILURE):
    1. ROLE CONTEXT: The problem MUST be strictly related to '{job_role}'.
    2. TECHNOLOGY LOCK: The code requested MUST strictly be for '{category}'. Do NOT deviate.
    3. ZERO THEORY: NEVER ask "What is", "Define", or "Explain". Must require EXECUTABLE CODE.
    4. UNIQUE SCENARIO: Provide a fresh scenario. DO NOT use these: {avoid_text}
    {test_case_rule}
    6. Return EXACTLY as a valid JSON object. No markdown.

    JSON Format Required:
    {{
        "question": "Problem Statement: Write a {category} program for our {job_role} architecture that... \\n\\nConstraints: ...",
        "ideal_answer": "The optimal {category} code solution.",
        "mandatory_keywords": "relevant syntax",
        "test_cases": [ ["get_a get_b x", "2"], ["hello world", "0"], ["get_x", "1"] ]
    }}
    """

# =========================================================
# 9. MAIN ROUTER & API ENGINE
# =========================================================
def get_smart_question(category, difficulty, seen_list=None, interview_type="Theory", job_role="Software Engineer"):
    if seen_list is None:
        seen_list = []

    print("\n" + "="*50)
    print(f"🎯 NEW QUESTION REQUEST | Role: {job_role} | Type: {interview_type} | Total Seen: {len(seen_list)}")
    print("="*50)

    # Database check (Theory or Coding DB based on type) — now role-aware too
    if len(seen_list) == 0:
        print(f"⚡ [X-RAY] CANDIDATE'S FIRST QUESTION! Checking {interview_type} Database for instant start...")
        db_q = get_fallback_question(category, difficulty, seen_list, interview_type, job_role)
        if db_q:
            print("⚡ [X-RAY] Success! Instant question loaded from DB.")
            return db_q
        else:
            print("⚡ [X-RAY] DB is EMPTY for this category/role. Falling back to APIs to build DB...")

    if not check_internet():
        print("🌐 [X-RAY] Internet OFFLINE! Forcing Database fallback...")
        db_q = get_fallback_question(category, difficulty, seen_list, interview_type, job_role)
        return db_q if db_q else "SYSTEM ERROR: Internet offline and Database is empty."

    avoid_text = "\n".join([f"- {q}" for q in seen_list]) if seen_list else "None"

    for attempt in range(3):
        random_seed = random.randint(1, 1000)

        # Passing job_role into both generators
        if interview_type == "Coding":
            prompt = generate_coding_prompt(category, difficulty, avoid_text, attempt, random_seed, job_role)
        else:
            prompt = generate_theory_prompt(category, difficulty, avoid_text, attempt, random_seed, job_role)

        print(f"\n🔄 GENERATION ATTEMPT {attempt + 1}/3 ...")

        # --- ENGINE 1: GROQ ---
        print(" 🟢 [ENGINE 1] Routing to Groq...")
        for index, key in enumerate(GEN_GROQ_KEYS): 
            if not key or key.startswith("YOUR_"): continue
            try:
                print(f"  -> Testing Groq Key {index + 1}...")
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": prompt}], "temperature": 0.8, "response_format": {"type": "json_object"}, "max_tokens": 2048}
                res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=8.0)
                res.raise_for_status()

                parsed = parse_json_response(res.json()["choices"][0]["message"]["content"].strip())
                if parsed and "question" in parsed:
                    question_text = parsed["question"].strip()
                    ideal_ans = parsed.get("ideal_answer", "")
                    keywords = parsed.get("mandatory_keywords", "")
                    test_cases_json = json.dumps(parsed.get("test_cases", []))
                    print(f"  🔍 [X-RAY] Groq returned {len(parsed.get('test_cases', []))} raw test cases.")

                    is_dup, score = is_duplicate(question_text, seen_list)
                    if not is_dup:
                        print(f" 🟢 [ENGINE 1] SUCCESS (Groq Key {index + 1})")
                        save_question_to_db(category, difficulty, interview_type, question_text, ideal_ans, keywords, test_cases_json, job_role)
                        return question_text
            except Exception as e:
                print(f"  ⚠️ [X-RAY ERROR] Groq Key {index + 1} Failed: {e}")

        # --- ENGINE 2: GEMINI ---
        print(" 🔵 [ENGINE 2] Routing to Gemini...")
        for index, key in enumerate(GEN_GEMINI_KEYS):
            if not key or key.startswith("YOUR_"): continue
            try:
                print(f"  -> Testing Gemini Key {index + 1}...")
                client = genai.Client(api_key=key)
                response = client.models.generate_content(model='gemini-3.5-flash', contents=prompt)
                parsed = parse_json_response(response.text.strip())
                
                if parsed and "question" in parsed:
                    question_text = parsed["question"].strip()
                    ideal_ans = parsed.get("ideal_answer", "")
                    keywords = parsed.get("mandatory_keywords", "")
                    test_cases_json = json.dumps(parsed.get("test_cases", []))
                    print(f"  🔍 [X-RAY] Gemini returned {len(parsed.get('test_cases', []))} raw test cases.")

                    is_dup, score = is_duplicate(question_text, seen_list)
                    if not is_dup:
                        print(f" 🔵 [ENGINE 2] SUCCESS (Gemini Key {index + 1})")
                        save_question_to_db(category, difficulty, interview_type, question_text, ideal_ans, keywords, test_cases_json, job_role)
                        return question_text
            except Exception as e:
                print(f"  ⚠️ [X-RAY ERROR] Gemini Key {index + 1} Failed: {e}")

        # --- ENGINE 3: COHERE ---
        print(" 🟣 [ENGINE 3] Routing to Cohere...")
        if GEN_COHERE_KEY and not GEN_COHERE_KEY.startswith("YOUR_"):
            try:
                headers = {"Authorization": f"Bearer {GEN_COHERE_KEY}", "Content-Type": "application/json"}
                payload = {"model": "command-r7b-12-2024", "message": prompt, "temperature": 0.9, "max_tokens": 2048}
                res = requests.post("https://api.cohere.com/v1/chat", headers=headers, json=payload, timeout=8.0)
                res.raise_for_status()

                parsed = parse_json_response(res.json()["text"].strip())
                if parsed and "question" in parsed:
                    question_text = parsed["question"].strip()
                    ideal_ans = parsed.get("ideal_answer", "")
                    keywords = parsed.get("mandatory_keywords", "")
                    test_cases_json = json.dumps(parsed.get("test_cases", []))
                    print(f"  🔍 [X-RAY] Cohere returned {len(parsed.get('test_cases', []))} raw test cases.")

                    is_dup, score = is_duplicate(question_text, seen_list)
                    if not is_dup:
                        print(" 🟣 [ENGINE 3] SUCCESS (Cohere)")
                        save_question_to_db(category, difficulty, interview_type, question_text, ideal_ans, keywords, test_cases_json, job_role)
                        return question_text
            except Exception as e:
                print(f"  ⚠️ [X-RAY ERROR] Cohere Failed: {e}")

        print(f"❌ Attempt {attempt + 1} Failed to produce a unique question. Retrying...")

    print("\n⚠️ [X-RAY] ALL AI ENGINES EXHAUSTED OR FAILED TO BE UNIQUE!")
    print("🗄️ [X-RAY] Activating Emergency Database Fallback...")

    db_fallback_q = get_fallback_question(category, difficulty, seen_list, interview_type, job_role)

    if db_fallback_q:
        return db_fallback_q
    else:
        print("🚨 [FATAL] DB is also empty/exhausted!")
        return "Since you selected this topic, can you write a functional code snippet related to the most complex concept you know about it?"

# =========================================================
# 10. TEST SCRIPT
# =========================================================
if __name__ == "__main__":
    test_seen = []

    # Picked a job role dynamically from ROLES_DATA so it isn't hardcoded
    dynamic_test_role = random.choice(list(ROLES_DATA.keys())) if ROLES_DATA else "Software Engineer"
    print(f"\n[TESTING CONTEXT] Selected Role from DB: {dynamic_test_role}")

    print("\n=== TESTING THEORY QUESTION ===")
    q1 = get_smart_question("Machine Learning", "Foundation", test_seen, interview_type="Theory", job_role=dynamic_test_role)
    print(f"\nOUTPUT Q1: {q1}\n")
    test_seen.append(q1)

    print("\n=== TESTING CODING QUESTION ===")
    q2 = get_smart_question("Python Algorithms", "Applied", test_seen, interview_type="Coding", job_role=dynamic_test_role)
    print(f"\nOUTPUT Q2: {q2}\n")