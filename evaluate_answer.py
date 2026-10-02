import json
import requests
import re
import sqlite3
import difflib
import warnings
import logging
from google import genai

# =========================================================
# 1. API KEYS SETUP (Evaluation Pools)
# =========================================================
from config import EVAL_GROQ_KEYS, EVAL_GEMINI_KEYS, EVAL_COHERE_KEY

DB_NAME = "theory_questions.db"

# Suppress unnecessary third-party warnings
warnings.filterwarnings("ignore")
logging.getLogger("google").setLevel(logging.ERROR)

VALID_STATUSES = {"Correct", "Partial", "Wrong", "Incomplete"}
MIN_ANSWER_LENGTH = 15

# Common phrases used when a candidate skips or doesn't know the answer
NON_ANSWER_PHRASES = [
    "i don't know", "i do not know", "dont know", "idk", "no idea",
    "not sure", "skip", "pass", "na", "n/a", "nhi aata", "nahi aata",
    "pata nahi", "pta nhi", "nothing"
]


# =========================================================
# 2. SMART JSON CLEANER
# =========================================================
def parse_json_response(ai_text):
    try:
        match = re.search(r'\{.*\}', ai_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(ai_text)
    except Exception as e:
        print(f"  ⚠️ [X-RAY ERROR] JSON Parsing Failed. Raw text: {ai_text[:60]}...")
        return None


# =========================================================
# 3. DATABASE FETCH (Used ONLY for NLP Emergency Fallback)
# =========================================================
def get_question_details(question_text):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ideal_answer, mandatory_keywords FROM interview_questions WHERE question=?",
            (question_text,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            print(f" 🗄️ [DB-X-RAY] ✅ Fetched Ideal Answer ({len(row[0] or '')} chars) & Keywords for Fallback.")
            return row[0] if row[0] else "", row[1] if row[1] else ""
        else:
            print(" 🗄️ [DB-X-RAY] ⚠️ Question not found in DB. Using blank references.")
            return "", ""
    except Exception as e:
        print(f" 🗄️ [DB-X-RAY ERROR] Fetch failed: {e}")
        return "", ""


# =========================================================
# 4. PYTHON LOCAL CHECKS (Filler Words & Non-Answer Detection)
# =========================================================
def analyze_filler_words(answer):
    filler_words = ["umm", "uh", "like", "basically", "actually", "literally", "sort of", "kind of"]
    words = answer.lower().split()
    count = sum(1 for w in words if w in filler_words)
    print(f" 🐍 [PYTHON-X-RAY] Filler words detected: {count}")
    return count


def is_non_answer(answer_text):
    """Detects if the candidate explicitly stated they do not know the answer."""
    lower_ans = answer_text.lower().strip()
    # If the answer is relatively short and contains a direct 'I don't know' phrase
    if len(lower_ans.split()) <= 15:
        for phrase in NON_ANSWER_PHRASES:
            if phrase in lower_ans:
                return True
    return False


# =========================================================
# 5. NLP EMERGENCY FALLBACK (Triggered ONLY when all AI APIs fail)
# =========================================================
def nlp_emergency_evaluation(user_answer, ideal_answer, mandatory_keywords):
    print("\n⚠️ [X-RAY] ALL AI ENGINES DOWN! Activating NLP Emergency Fallback...")

    if not ideal_answer and not mandatory_keywords:
        print(" ❌ [NLP-X-RAY] ERROR: Ideal answer and keywords missing in DB! Cannot evaluate properly.")
        return {
            "status": "Incomplete",
            "technical_score": 0.0,
            "clarity_feedback": "NLP evaluation failed.",
            "grammar_feedback": "Not evaluated.",
            "overall_feedback": "System overloaded and reference data missing. Manual review required."
        }

    # 1. Similarity Calculation
    similarity = difflib.SequenceMatcher(None, user_answer.lower(), ideal_answer.lower()).ratio()
    print(f" 🧮 [NLP-X-RAY] Mathematical Similarity: {similarity*100:.1f}%")

    # 2. Keyword Checking
    keywords_list = [k.strip().lower() for k in mandatory_keywords.split(",") if k.strip()]
    matched_kws = [k for k in keywords_list if k in user_answer.lower()]
    missing_kws = [k for k in keywords_list if k not in user_answer.lower()]

    print(f" 🧮 [NLP-X-RAY] Matched Keywords: {len(matched_kws)}/{len(keywords_list)} -> {matched_kws}")

    # 3. Decision Logic
    has_keywords = len(keywords_list) > 0
    passed_keywords = has_keywords and (len(matched_kws) >= (len(keywords_list) / 2))

    if similarity > 0.45 or passed_keywords:
        status = "Correct"
        feedback = f"Great effort! You captured the core concepts. Missing keywords: {', '.join(missing_kws) if missing_kws else 'None'}."
    elif len(user_answer.split()) > 10 and (len(matched_kws) > 0 or similarity > 0.25):
        status = "Partial"
        feedback = f"You mentioned relevant terms but lacked complete depth. You missed addressing: {', '.join(missing_kws) if missing_kws else 'key details'}."
    else:
        status = "Wrong"
        feedback = f"Your response lacked technical accuracy and depth. Key concepts missed: {', '.join(missing_kws) if missing_kws else 'Multiple core concepts'}."

    print(f" 🧮 [NLP-X-RAY] Final NLP Verdict -> Status: {status}")

    return {
        "status": status,
        "technical_score": round(similarity * 10, 1),
        "clarity_feedback": "Evaluated via mathematical NLP fallback due to high network load.",
        "grammar_feedback": "Not evaluated.",
        "overall_feedback": feedback
    }


# =========================================================
# 6. MAIN EVALUATION ENGINE
# =========================================================
def evaluate_candidate_answer(question, user_answer, difficulty="Applied"):
    print("\n" + "="*50)
    print("🧠 EVALUATING CANDIDATE ANSWER")
    print(f"🔍 [X-RAY] Question: {question[:60]}... | Difficulty: {difficulty}")
    print("="*50)

    cleaned_answer = (user_answer or "").strip()

    # Check 1: Catch overly brief responses
    if len(cleaned_answer) < MIN_ANSWER_LENGTH:
        print(f" ❌ [X-RAY] Answer too short (< {MIN_ANSWER_LENGTH} chars). Marking as Wrong without API call.")
        return {
            "status": "Wrong",
            "overall_feedback": "Invalid Submission: Your response is too brief or lacks sufficient technical explanation to be evaluated. Please provide a complete conceptual answer."
        }

    # Check 2: Catch explicit 'I don't know' or skip responses locally
    if is_non_answer(cleaned_answer):
        print(" ❌ [X-RAY] Candidate explicitly stated they do not know the answer. Marking as Wrong without API call.")
        return {
            "status": "Wrong",
            "overall_feedback": "It appears you did not know the answer to this question. Review the core concepts related to this topic and try again in your next practice session."
        }

    # Notice: We DO NOT pass ideal_answer or mandatory_keywords into the AI prompt.
    # This prevents smaller models (like Cohere command-r7b) from hallucinating that the
    # candidate wrote the reference answer.
    prompt = f"""
    You are a strict, objective, and constructive Senior Technical Interviewer evaluating a candidate's conceptual answer.
    Candidate Level: {difficulty}
    
    Interview Question:
    "{question}"
    
    Candidate's Submitted Answer:
    "{cleaned_answer}"
    
    STRICT EVALUATION RULES:
    1. Independent Verification: Judge ONLY what the candidate actually wrote in 'Candidate's Submitted Answer'. Do not assume they know concepts they did not explicitly mention.
    2. When to mark "Wrong": If the answer is factually incorrect, irrelevant, vague filler, states they don't know, or completely misses the technical point of the question, you MUST set status to "Wrong".
    3. When to mark "Partial": If the candidate identifies the basic direction or mentions a relevant concept but fails to explain how it works or misses major architectural parts, set status to "Partial".
    4. When to mark "Correct": If the candidate accurately and clearly explains the core technical solution appropriate for the '{difficulty}' level (ignoring minor spelling/grammar typos), set status to "Correct".
    5. Constructive Feedback: Directly tell the candidate what they got right and what specific technical concepts they missed or need to improve.

    Return EXACTLY a valid JSON object matching this schema (choose strictly ONE status from "Correct", "Partial", or "Wrong"):
    {{
        "status": "<Correct or Partial or Wrong>",
        "overall_feedback": "<Your clear, objective technical feedback here>"
    }}
    """

    def _valid(parsed):
        if not parsed or "status" not in parsed:
            return False
        if parsed["status"] not in VALID_STATUSES:
            print(f"  ⚠️ [X-RAY] AI returned an invalid status: '{parsed['status']}'. Rejecting response.")
            return False
        return True

    # --- ENGINE 1: GROQ ---
    print(" 🟢 [ENGINE 1] Routing to Groq for Evaluation...")
    for index, key in enumerate(EVAL_GROQ_KEYS):
        if not key or key.startswith("YOUR_"):
            continue
        try:
            print(f"  -> Testing Groq Key {index + 1}...")
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {
                "model": "openai/gpt-oss-20b",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "max_tokens": 2048
            }
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=8.0)
            res.raise_for_status()

            parsed = parse_json_response(res.json()["choices"][0]["message"]["content"].strip())
            if _valid(parsed):
                print(f" 🟢 [ENGINE 1] SUCCESS (Groq Key {index + 1}) -> Status: {parsed['status']}")
                return parsed
            else:
                print(f"  ⚠️ [X-RAY] Groq Key {index + 1} did not return usable JSON.")
        except Exception as e:
            print(f"  ⚠️ [X-RAY ERROR] Groq Key {index + 1} Failed: {e}")

# --- ENGINE 2: GEMINI ---
    print(" 🔵 [ENGINE 2] Routing to Gemini for Evaluation...")
    for index, key in enumerate(EVAL_GEMINI_KEYS):
        if not key or key.startswith("YOUR_"):
            continue
        try:
            print(f"  -> Testing Gemini Key {index + 1}...")
            client = genai.Client(api_key=key)
            interaction = client.interactions.create(
                model="gemini-3.5-flash",
                input=prompt
            )

            parsed = parse_json_response(interaction.output_text.strip())
            if _valid(parsed):
                print(f" 🔵 [ENGINE 2] SUCCESS (Gemini Key {index + 1}) -> Status: {parsed['status']}")
                return parsed
            else:
                print(f"  ⚠️ [X-RAY] Gemini Key {index + 1} did not return usable JSON.")
        except Exception as e:
            print(f"  ⚠️ [X-RAY ERROR] Gemini Key {index + 1} Failed: {e}")

    # --- ENGINE 3: COHERE ---
    print(" 🟣 [ENGINE 3] Routing to Cohere for Evaluation...")
    if EVAL_COHERE_KEY and not EVAL_COHERE_KEY.startswith("YOUR_"):
        try:
            headers = {"Authorization": f"Bearer {EVAL_COHERE_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "command-r7b-12-2024",
                "message": prompt,
                "temperature": 0.1,
                "max_tokens": 2048
            }
            res = requests.post("https://api.cohere.com/v1/chat", headers=headers, json=payload, timeout=8.0)
            res.raise_for_status()

            parsed = parse_json_response(res.json()["text"].strip())
            if _valid(parsed):
                print(f" 🟣 [ENGINE 3] SUCCESS (Cohere) -> Status: {parsed['status']}")
                return parsed
            else:
                print("  ⚠️ [X-RAY] Cohere did not return usable JSON.")
        except Exception as e:
            print(f"  ⚠️ [X-RAY ERROR] Cohere Failed: {e}")
    else:
        print("  ⚠️ [X-RAY] Cohere key is not set or is a placeholder, skipping.")

    # --- ENGINE 4: NLP EMERGENCY FALLBACK ---
    print(" 🚨 [X-RAY] All three AI engines failed — fetching DB references and switching to NLP fallback...")
    ideal_answer, mandatory_keywords = get_question_details(question)
    return nlp_emergency_evaluation(cleaned_answer, ideal_answer, mandatory_keywords)


# =========================================================
# 7. SCORING SYSTEM (Used by UI)
# =========================================================
def calculate_score(evaluation_result):
    status = evaluation_result.get("status", "Incomplete")
    print(f" 🧮 [SCORE-X-RAY] Calculating score for status='{status}'...")
    if status == "Correct":
        return 1.0
    elif status == "Partial":
        return 0.5
    elif status == "Wrong":
        return -0.25
    return 0.0


# =========================================================
# 8. STANDALONE TEST BLOCK
# =========================================================
if __name__ == "__main__":
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT question, mandatory_keywords FROM interview_questions WHERE ideal_answer IS NOT NULL ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        t_question = row[0]
        hint_keywords = row[1]
        print(f"\n🔍 [TEST SETUP] Using Latest DB Question: {t_question}")
        print(f"🔑 [HINT] Mandatory keywords: {hint_keywords}")

        print("\n--- TEST CASE 1: Valid Concept Check ---")
        ans_1 = f"To structure this properly, we should define a common {hint_keywords} so that new notification types can be added without modifying existing code."
        res1 = evaluate_candidate_answer(t_question, ans_1)
        print(json.dumps(res1, indent=2))
        print(f"Points: {calculate_score(res1)}")

        print("\n--- TEST CASE 2: Failing / Vague Wrong Answer (Tests Cohere directly) ---")
        ans_2 = "We can just write multiple if-else statements inside the main class every time a new notification type is needed."
        res2 = evaluate_candidate_answer(t_question, ans_2)
        print(json.dumps(res2, indent=2))
        print(f"Points: {calculate_score(res2)}")
        
        print("\n--- TEST CASE 3: Explicit 'I don't know' Check (Tests Local Filter) ---")
        ans_3 = "I do not know the exact answer to this question right now."
        res3 = evaluate_candidate_answer(t_question, ans_3)
        print(json.dumps(res3, indent=2))
        print(f"Points: {calculate_score(res3)}")
    else:
        print("\n⚠️ [TEST ERROR]: No questions with an ideal_answer found in the database. Please run questions_generate.py first.")