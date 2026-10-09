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

RESUME_CATEGORY = "Resume Based"
DEFAULT_IDEAL = ("Candidate should logically explain their specific project architecture, practical "
                 "implementation, and any trade-offs faced.")
DEFAULT_KEYWORDS = "project, logic, architecture, implementation"

# in-memory backup (the DB is the main source of truth)
_REFERENCE_REGISTRY = {}

# Common phrases used when a candidate skips or doesn't know the answer
NON_ANSWER_PHRASES = [
    "i don't know", "i do not know", "dont know", "idk", "no idea",
    "not sure", "skip", "pass", "na", "n/a", "nhi aata", "nahi aata",
    "pata nahi", "pta nhi", "nothing"
]


# =========================================================
# 1B. REFERENCE ANSWER STORE (used for resume questions + NLP fallback + results screen)
# =========================================================
def norm_q(text):
    """Compare-safe version of a question: no '**Question:**', no markdown, one space, lowercase."""
    t = str(text or "").replace("**Question:**", " ")
    t = re.sub(r"[*_`#>]", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t.strip(" .?:;-")


def _connect():
    return sqlite3.connect(DB_NAME, timeout=10)


def _ensure_table(conn):
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
    try:
        conn.execute("ALTER TABLE interview_questions ADD COLUMN job_role TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def register_reference(question, ideal_answer, keywords, category=RESUME_CATEGORY,
                       difficulty="Applied", job_role="Resume"):
    """Stores question + ideal answer + keywords in the DB (and memory). Safe to call repeatedly."""
    q = str(question or "").replace("**Question:**", "").strip()
    if not q:
        return False
    ideal = str(ideal_answer or "").strip() or DEFAULT_IDEAL
    if isinstance(keywords, (list, tuple)):
        keywords = ", ".join(str(k) for k in keywords)
    kws = str(keywords or "").strip() or DEFAULT_KEYWORDS

    _REFERENCE_REGISTRY[norm_q(q)] = {"ideal_answer": ideal, "keywords": kws}
    try:
        conn = _connect()
        _ensure_table(conn)
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO interview_questions "
            "(category, difficulty, interview_type, job_role, question, ideal_answer, mandatory_keywords, test_cases) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (category, difficulty, "Theory", job_role, q, ideal, kws, "[]")
        )
        cur.execute("UPDATE interview_questions SET ideal_answer=?, mandatory_keywords=? WHERE question=?",
                    (ideal, kws, q))
        conn.commit()
        conn.close()
        print(f" 🗄️ [REF-X-RAY] Reference saved for: {q[:50]}...")
    except Exception as e:
        print(f" 🗄️ [REF-X-RAY ERROR] DB save failed (memory copy kept): {e}")
    return True


def get_reference(question):
    """Returns {"ideal_answer": str, "keywords": str}. Tolerant to spaces / '**Question:**' / markdown."""
    raw = str(question or "")
    clean = raw.replace("**Question:**", "").strip()
    key = norm_q(raw)

    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT ideal_answer, mandatory_keywords FROM interview_questions WHERE question=? OR question=?",
                    (clean, raw))
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT question, ideal_answer, mandatory_keywords FROM interview_questions")
            for dq, ia, kw in cur.fetchall():
                if norm_q(dq) == key:
                    row = (ia, kw)
                    break
        conn.close()
        if row and (row[0] or row[1]):
            return {"ideal_answer": row[0] or "", "keywords": row[1] or ""}
    except Exception as e:
        print(f" 🗄️ [REF-X-RAY] DB lookup failed: {e}")

    if key in _REFERENCE_REGISTRY:
        return dict(_REFERENCE_REGISTRY[key])
    close = difflib.get_close_matches(key, list(_REFERENCE_REGISTRY.keys()), n=1, cutoff=0.9)
    if close:
        return dict(_REFERENCE_REGISTRY[close[0]])
    return {"ideal_answer": "", "keywords": ""}


def _generate_reference_via_api(q_text):
    prompt = f"""
    You are an expert interviewer. For this technical question: "{q_text}"
    Provide:
    1. A brief 2-3 sentence human-like "ideal_answer".
    2. A comma-separated list of 3-5 "mandatory_keywords".
    Return ONLY a JSON object: {{"ideal_answer": "...", "mandatory_keywords": "..."}}
    """
    for key in EVAL_GEMINI_KEYS:
        if not key or key.startswith("YOUR_"):
            continue
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent"
            payload = {"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}}
            res = requests.post(url, params={"key": key}, json=payload, timeout=8.0)
            if res.status_code == 200:
                parsed = json.loads(res.json()["candidates"][0]["content"]["parts"][0]["text"])
                return (parsed.get("ideal_answer") or DEFAULT_IDEAL,
                        parsed.get("mandatory_keywords") or DEFAULT_KEYWORDS)
        except Exception as e:
            print(f"⚠️ [RESUME-DB ERROR] Failed to fetch AI answer: {e}")
    return DEFAULT_IDEAL, DEFAULT_KEYWORDS


def save_resume_questions_to_db(questions_list, category=None, difficulty="Applied",
                                interview_type="Theory", job_role="Resume"):
    """Backward-compatible. Makes sure every resume question has a stored reference answer.
    Skips the API call if resume_engine already registered one. Never raises."""
    saved = []
    for q_text in questions_list or []:
        try:
            q_text = str(q_text).replace("**Question:**", "").strip()
            if not q_text:
                continue
            ref = get_reference(q_text)
            if ref["ideal_answer"]:
                saved.append(q_text)
                continue
            print(f"🧠 [RESUME-DB] Generating Ideal Answer for DB: {q_text[:40]}...")
            ideal, kws = _generate_reference_via_api(q_text)
            register_reference(q_text, ideal, kws, category=RESUME_CATEGORY,
                               difficulty=difficulty or "Applied", job_role="Resume")
            saved.append(q_text)
        except Exception as e:
            print(f"❌ [RESUME-DB ERROR] {e}")
            saved.append(q_text)
    return saved


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
        print(f"  ⚠️ [X-RAY ERROR] JSON Parsing Failed. Raw text: {str(ai_text)[:60]}...")
        return None


# =========================================================
# 3. REFERENCE FETCH (Used ONLY for NLP Emergency Fallback)
# =========================================================
def get_question_details(question_text):
    ref = get_reference(question_text)
    if ref["ideal_answer"] or ref["keywords"]:
        print(f" 🗄️ [DB-X-RAY] ✅ Fetched Ideal Answer ({len(ref['ideal_answer'])} chars) & Keywords for Fallback.")
    else:
        print(" 🗄️ [DB-X-RAY] ⚠️ Question not found in DB. Using blank references.")
    return ref["ideal_answer"], ref["keywords"]


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

    similarity = difflib.SequenceMatcher(None, user_answer.lower(), (ideal_answer or "").lower()).ratio()
    print(f" 🧮 [NLP-X-RAY] Mathematical Similarity: {similarity*100:.1f}%")

    keywords_list = [k.strip().lower() for k in (mandatory_keywords or "").split(",") if k.strip()]
    matched_kws = [k for k in keywords_list if k in user_answer.lower()]
    missing_kws = [k for k in keywords_list if k not in user_answer.lower()]

    print(f" 🧮 [NLP-X-RAY] Matched Keywords: {len(matched_kws)}/{len(keywords_list)} -> {matched_kws}")

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

    if len(cleaned_answer) < MIN_ANSWER_LENGTH:
        print(f" ❌ [X-RAY] Answer too short (< {MIN_ANSWER_LENGTH} chars). Marking as Wrong without API call.")
        return {
            "status": "Wrong",
            "overall_feedback": "Invalid Submission: Your response is too brief or lacks sufficient technical explanation to be evaluated. Please provide a complete conceptual answer."
        }

    if is_non_answer(cleaned_answer):
        print(" ❌ [X-RAY] Candidate explicitly stated they do not know the answer. Marking as Wrong without API call.")
        return {
            "status": "Wrong",
            "overall_feedback": "It appears you did not know the answer to this question. Review the core concepts related to this topic and try again in your next practice session."
        }

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
            try:
                resp = client.models.generate_content(model="gemini-3.5-flash", contents=prompt)
                raw_text = resp.text
            except Exception as inner:
                print(f"  ⚠️ [X-RAY] generate_content failed ({inner}); trying interactions API...")
                interaction = client.interactions.create(model="gemini-3.5-flash", input=prompt)
                raw_text = interaction.output_text

            parsed = parse_json_response((raw_text or "").strip())
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

        print("\n--- TEST CASE 2: Failing / Vague Wrong Answer ---")
        ans_2 = "We can just write multiple if-else statements inside the main class every time a new notification type is needed."
        res2 = evaluate_candidate_answer(t_question, ans_2)
        print(json.dumps(res2, indent=2))
        print(f"Points: {calculate_score(res2)}")

        print("\n--- TEST CASE 3: Explicit 'I don't know' Check ---")
        ans_3 = "I do not know the exact answer to this question right now."
        res3 = evaluate_candidate_answer(t_question, ans_3)
        print(json.dumps(res3, indent=2))
        print(f"Points: {calculate_score(res3)}")
    else:
        print("\n⚠️ [TEST ERROR]: No questions with an ideal_answer found in the database. Please run questions_generate.py first.")
