import streamlit as st
import sqlite3
import time
import json
import threading
import traceback
import concurrent.futures
from streamlit.runtime.scriptrunner import add_script_run_ctx
import streamlit.components.v1 as components
from streamlit_ace import st_ace

from roles_db import ROLES_DATA
import questions_generate
import evaluate_answer
import code_evaluate

TIME_LIMITS = {"Foundation": 90, "Applied": 180, "Advanced": 300, "Expert": 420}
TOTAL_QUESTIONS = 5

# =========================================================
# UI THEME & PRESENTATION HELPERS
# (Pure styling / decorative rendering only — no session_state writes,
#  no control flow, no business logic lives in this section.)
# =========================================================

def inject_theme():
    """Injects the global dark theme (colors, fonts, widget skinning) used across
    every screen. Only changes appearance — never touches state or logic."""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

    :root {
        --bg: #0B0E14;
        --surface: #151922;
        --surface-soft: rgba(21, 25, 34, 0.7);
        --border: rgba(255, 255, 255, 0.08);
        --border-hover: rgba(255, 107, 107, 0.45);
        --text-primary: #F4F4F6;
        --text-secondary: #8B8F9C;
        --coral: #FF6B6B;
        --amber: #FFA94D;
        --teal: #4ECDC4;
        --gradient: linear-gradient(135deg, #FF6B6B 0%, #FFA94D 100%);
    }

    html, body, [data-testid="stAppViewContainer"], .stApp {
        background: var(--bg) !important;
        color: var(--text-primary) !important;
        font-family: 'Inter', sans-serif !important;
    }

    [data-testid="stHeader"] { background: transparent !important; }

    .main .block-container {
        max-width: 900px;
        margin: 0 auto;
        padding-top: 2.2rem;
        padding-bottom: 4rem;
    }

    h1, h2, h3, h4 {
        font-family: 'Sora', sans-serif !important;
        color: var(--text-primary) !important;
        font-weight: 700 !important;
    }

    p, span, label, li { color: var(--text-primary); }

    /* Buttons */
    .stButton > button {
        border-radius: 12px !important;
        border: 1px solid var(--border) !important;
        background: var(--surface) !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        font-family: 'Inter', sans-serif !important;
        transition: all 0.18s ease !important;
        padding: 0.6rem 1.2rem !important;
    }
    .stButton > button:hover {
        border-color: var(--border-hover) !important;
        transform: translateY(-1px);
        box-shadow: 0 8px 20px rgba(255, 107, 107, 0.12);
    }
    .stButton > button:active { transform: scale(0.98); }

    .stButton > button[kind="primary"] {
        background: var(--gradient) !important;
        border: none !important;
        color: #1A0F0A !important;
        box-shadow: 0 8px 24px rgba(255, 107, 107, 0.25);
    }
    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 10px 28px rgba(255, 107, 107, 0.4);
        transform: translateY(-2px);
    }

    /* Selectbox / Radio / Text areas */
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stTextArea"] textarea {
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: 12px !important;
        color: var(--text-primary) !important;
    }
    [data-testid="stTextArea"] textarea {
        font-family: 'Inter', sans-serif !important;
        padding: 14px !important;
    }
    [data-testid="stTextArea"] textarea:focus {
        border-color: var(--coral) !important;
        box-shadow: 0 0 0 1px var(--coral) !important;
    }

    /* Expander (results accordion) */
    [data-testid="stExpander"] {
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: 16px !important;
        margin-bottom: 14px !important;
        overflow: hidden;
    }
    [data-testid="stExpander"] summary {
        font-family: 'Sora', sans-serif !important;
        font-weight: 600 !important;
    }

    /* Alerts */
    [data-testid="stAlert"] {
        border-radius: 12px !important;
        font-family: 'Inter', sans-serif !important;
        border: 1px solid var(--border) !important;
    }

    /* Sidebar (Rough Pad) */
    [data-testid="stSidebar"] {
        background: var(--surface) !important;
        border-right: 1px solid var(--border) !important;
    }

    /* Step progress bar (lobby) */
    .step-track { display: flex; align-items: center; gap: 8px; margin-bottom: 1.8rem; }
    .step-seg { height: 4px; flex: 1; border-radius: 999px; background: var(--border); overflow: hidden; }
    .step-seg.filled { background: var(--gradient); }
    .step-label { font-size: 13px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace; white-space: nowrap; }

    /* Difficulty timeline */
    .diff-track { display: flex; align-items: center; justify-content: space-between; margin: 1.4rem 0; position: relative; }
    .diff-track::before {
        content: ""; position: absolute; top: 22px; left: 24px; right: 24px; height: 2px;
        background: var(--border); z-index: 0;
    }
    .diff-node { position: relative; z-index: 1; display: flex; flex-direction: column; align-items: center; gap: 8px; flex: 1; }
    .diff-circle {
        width: 44px; height: 44px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-family: 'JetBrains Mono', monospace; font-weight: 600;
        border: 2px solid var(--border); background: var(--surface); color: var(--text-secondary);
    }
    .diff-circle.active {
        border-color: var(--coral); background: var(--gradient); color: #1A0F0A;
        box-shadow: 0 0 0 6px rgba(255, 107, 107, 0.12);
    }
    .diff-name { font-size: 13px; color: var(--text-secondary); }
    .diff-name.active { color: var(--text-primary); font-weight: 600; }

    /* Circular countdown timer */
    .timer-wrap { display: flex; justify-content: flex-end; margin-bottom: 0.6rem; }
    .timer-ring-box { position: relative; width: 64px; height: 64px; }
    .timer-ring-box svg { transform: rotate(-90deg); }
    .timer-ring-bg { fill: none; stroke: var(--border); stroke-width: 5; }
    .timer-ring-fg {
        fill: none; stroke: var(--teal); stroke-width: 5; stroke-linecap: round;
        transition: stroke-dashoffset 0.9s linear, stroke 0.3s ease;
    }
    .timer-ring-text {
        position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
        font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 13px; color: var(--text-primary);
    }
    .timer-critical .timer-ring-box { animation: pulseGlow 1s ease-in-out infinite; }
    @keyframes pulseGlow {
        0%, 100% { filter: drop-shadow(0 0 0 rgba(255,107,107,0)); }
        50% { filter: drop-shadow(0 0 10px rgba(255,107,107,0.6)); }
    }

    /* Status badges (results) */
    .status-pill {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 4px 12px; border-radius: 999px;
        font-size: 12px; font-weight: 600; font-family: 'JetBrains Mono', monospace;
        border: 1px solid transparent; margin-bottom: 10px;
    }
    .status-pill.correct { background: rgba(78,205,196,0.12); color: var(--teal); border-color: rgba(78,205,196,0.35); }
    .status-pill.partial { background: rgba(255,169,77,0.12); color: var(--amber); border-color: rgba(255,169,77,0.35); }
    .status-pill.wrong { background: rgba(255,107,107,0.12); color: var(--coral); border-color: rgba(255,107,107,0.35); }
    .status-pill.incomplete { background: rgba(139,143,156,0.12); color: var(--text-secondary); border-color: rgba(139,143,156,0.35); }

    /* Score ring (results hero) */
    .score-hero { display: flex; flex-direction: column; align-items: center; gap: 6px; margin: 1rem 0 2rem; }
    .score-ring-box { position: relative; width: 160px; height: 160px; }
    .score-ring-box svg { transform: rotate(-90deg); }
    .score-ring-bg { fill: none; stroke: var(--border); stroke-width: 10; }
    .score-ring-fg { fill: none; stroke-width: 10; stroke-linecap: round; stroke: url(#scoreGradient); }
    .score-ring-text {
        position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center;
    }
    .score-ring-text .num { font-family: 'Sora', sans-serif; font-size: 34px; font-weight: 800; }
    .score-ring-text .den { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-secondary); }

    /* Processing loader */
    .loader-wrap { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 4rem 0; gap: 1rem; }
    .orbit { position: relative; width: 90px; height: 90px; }
    .orbit-core { position: absolute; inset: 0; margin: auto; width: 14px; height: 14px; border-radius: 50%; background: var(--gradient); }
    .orbit-dot { position: absolute; width: 10px; height: 10px; border-radius: 50%; background: var(--coral); top: 0; left: 50%; transform-origin: 5px 45px; animation: orbitSpin 1.6s linear infinite; }
    .orbit-dot:nth-child(2) { background: var(--amber); animation-duration: 2.1s; }
    .orbit-dot:nth-child(3) { background: var(--teal); animation-duration: 2.6s; animation-direction: reverse; }
    @keyframes orbitSpin { from { transform: rotate(0deg) translateY(0) rotate(0deg); } to { transform: rotate(360deg) translateY(0) rotate(-360deg); } }
    .loader-title { font-family: 'Sora', sans-serif; font-weight: 700; font-size: 19px; }
    .loader-sub { color: var(--text-secondary); font-size: 14px; }

    /* Code editor label strip */
        /* Rules & Guidelines card (shown before the interview starts) */
    .rules-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 22px 26px;
        margin: 1rem 0 1.5rem;
    }
    .rules-section { margin-bottom: 18px; }
    .rules-section:last-child { margin-bottom: 0; }
    .rules-section-title {
        font-family: 'Sora', sans-serif;
        font-weight: 700;
        font-size: 15px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .rules-list { list-style: none; margin: 0; padding: 0; }
    .rules-list li {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 6px 0;
        font-size: 14px;
        color: var(--text-primary);
        line-height: 1.5;
    }
    .rules-list li .rule-text {
    flex: 1;
    }
    .rules-list li .bullet-icon {
        flex-shrink: 0;
        width: 20px;
        height: 20px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: 700;
        margin-top: 1px;
    }
    .rules-list li .bullet-icon.coral { background: rgba(255,107,107,0.15); color: var(--coral); }
    .rules-list li .bullet-icon.amber { background: rgba(255,169,77,0.15); color: var(--amber); }
    .rules-list li .bullet-icon.teal { background: rgba(78,205,196,0.15); color: var(--teal); }
    .code-strip {
        display: flex; justify-content: space-between; align-items: center;
        background: var(--surface); border: 1px solid var(--border); border-bottom: none;
        border-radius: 12px 12px 0 0; padding: 8px 14px;
        font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text-secondary);
    }
    </style>
    """, unsafe_allow_html=True)


def render_step_progress(current_step, total_steps=4):
    """Decorative only: draws the top progress bar for the 3-step lobby wizard."""
    segs = "".join(
        f'<div class="step-seg {"filled" if i < current_step else ""}"></div>'
        for i in range(total_steps)
    )
    st.markdown(
        f'<div class="step-track"><span class="step-label">Step {current_step} of {total_steps}</span>{segs}</div>',
        unsafe_allow_html=True
    )


def render_difficulty_timeline(selected_difficulty):
    """Decorative only: shows the 4 difficulty levels as a connected timeline,
    highlighting whichever one the existing st.selectbox has chosen."""
    levels = ["Foundation", "Applied", "Advanced", "Expert"]
    nodes = ""
    for i, lvl in enumerate(levels, start=1):
        active = (lvl == selected_difficulty)
        circle_cls = "diff-circle active" if active else "diff-circle"
        name_cls = "diff-name active" if active else "diff-name"
        nodes += f'<div class="diff-node"><div class="{circle_cls}">{i:02d}</div><div class="{name_cls}">{lvl}</div></div>'
    st.markdown(f'<div class="diff-track">{nodes}</div>', unsafe_allow_html=True)


def render_status_badge(status):
    """Decorative only: returns an HTML pill for a given status string."""
    cls_map = {"Correct": "correct", "Partial": "partial", "Wrong": "wrong", "Incomplete": "incomplete"}
    icon_map = {"Correct": "✓", "Partial": "◐", "Wrong": "✕", "Incomplete": "–"}
    cls = cls_map.get(status, "incomplete")
    icon = icon_map.get(status, "–")
    st.markdown(f'<span class="status-pill {cls}">{icon} {status}</span>', unsafe_allow_html=True)

def render_rules_panel():
    """Decorative only: shows the candidate a bullet-point explanation of how
    the AI interview works, how to operate it, and the exact marking scheme."""
    html = """
    <div class="rules-card">

        <div class="rules-section">
            <div class="rules-section-title">🧭 How this interview works</div>
            <ul class="rules-list">
                <li><span class="bullet-icon coral">1</span><span class="rule-text">You'll be asked <b>5 questions</b> in total, generated fresh by AI based on your selected role, skill and difficulty — no two attempts are exactly the same.</span></li>
                <li><span class="bullet-icon coral">2</span><span class="rule-text">Depending on the format you chose, questions are either <b>Theory</b> (answer by typing or speaking) or <b>Coding</b> (write and run real code in the editor).</span></li>
                <li><span class="bullet-icon coral">3</span><span class="rule-text">Once you move to the next question, you <b>cannot go back</b> to a previous one.</span></li>
            </ul>
        </div>

        <div class="rules-section">
            <div class="rules-section-title">🎛️ Operating the interview</div>
            <ul class="rules-list">
                <li><span class="bullet-icon teal">1</span><span class="rule-text">The AI reads each question aloud automatically.</span></li>
                <li><span class="bullet-icon teal">2</span><span class="rule-text">For Theory questions: type your answer, or use the <b>mic button</b> — on desktop, hold <b>Ctrl + Shift</b> to speak; on mobile, just <b>tap once to start</b> and <b>tap again to stop</b>.</span></li>
                <li><span class="bullet-icon teal">3</span><span class="rule-text">For Coding questions: write your solution in the editor and click <b>Run Code</b> to test it as many times as you want before submitting — running code does not use up an attempt.</span></li>
                <li><span class="bullet-icon teal">4</span><span class="rule-text">Use the <b>Rough Pad</b> in the sidebar to jot down notes or work through logic — it is not submitted or scored.</span></li>
                <li><span class="bullet-icon teal">5</span><span class="rule-text">Click <b>Save & Next Question</b> (or <b>Final Submit Exam</b> on the last question) when you're ready to move on.</span></li>
            </ul>
        </div>

        <div class="rules-section">
            <div class="rules-section-title">⏱️ Timing</div>
            <ul class="rules-list">
                <li><span class="bullet-icon amber">1</span><span class="rule-text">Each question has a <b>countdown timer</b> based on the difficulty level — the ring in the top-right turns amber, then red, as time runs low.</span></li>
                <li><span class="bullet-icon amber">2</span><span class="rule-text">If the timer runs out, your current answer is auto-submitted as-is and the interview moves on.</span></li>
                <li><span class="bullet-icon amber">3</span><span class="rule-text">Staying inactive for too long is also treated the same as running out of time.</span></li>
            </ul>
        </div>

        <div class="rules-section">
            <div class="rules-section-title">🚫 Conduct during the test</div>
            <ul class="rules-list">
                <li><span class="bullet-icon coral">1</span><span class="rule-text">Switching tabs or minimizing the window is detected — doing so is logged as a <b>cheating attempt</b> and that question is marked wrong.</span></li>
                <li><span class="bullet-icon coral">2</span><span class="rule-text">Copy and paste are disabled inside the answer area and code editor.</span></li>
            </ul>
        </div>

        <div class="rules-section">
            <div class="rules-section-title">🤖 How answers are scored</div>
            <ul class="rules-list">
                <li><span class="bullet-icon teal">1</span><span class="rule-text">Theory answers are reviewed by AI for correctness and depth — minor typos are never penalized.</span></li>
                <li><span class="bullet-icon teal">2</span><span class="rule-text">Code answers run in a secure sandbox against test cases, then get an AI code review.</span></li>
                <li><span class="bullet-icon teal">3</span><span class="rule-text">Every answer gets one of four marks — <b>Correct: +1</b>, <b>Partial: +0.5</b>, <b>Wrong: -0.25</b>, <b>Incomplete (skipped/timed out): 0</b>.</span></li>
                <li><span class="bullet-icon teal">4</span><span class="rule-text">Your final report shows a total score out of 5, a status for every question, and detailed AI feedback on each answer.</span></li>
            </ul>
        </div>

    </div>
    """
    html = "\n".join(line.strip() for line in html.strip("\n").split("\n"))
    st.markdown(html, unsafe_allow_html=True)

def render_score_ring(score, max_score):
    """Decorative only: renders the circular score ring on the results screen,
    using the exact same already-computed score/max_score values as before."""
    pct = 0 if max_score == 0 else max(0.0, min(1.0, score / max_score))
    radius = 70
    circumference = 2 * 3.14159265 * radius
    offset = circumference * (1 - pct)
    st.markdown(f"""
    <div class="score-hero">
        <div class="score-ring-box">
            <svg width="160" height="160" viewBox="0 0 160 160">
                <defs>
                    <linearGradient id="scoreGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stop-color="#FF6B6B" />
                        <stop offset="100%" stop-color="#FFA94D" />
                    </linearGradient>
                </defs>
                <circle class="score-ring-bg" cx="80" cy="80" r="{radius}" />
                <circle class="score-ring-fg" cx="80" cy="80" r="{radius}"
                    stroke-dasharray="{circumference:.2f}" stroke-dashoffset="{offset:.2f}" />
            </svg>
            <div class="score-ring-text">
                <div class="num">{score:.2f}</div>
                <div class="den">/ {max_score} SCORE</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_loader(title, subtitle):
    """Decorative only: orbiting-dots loader shown on the processing screen."""
    st.markdown(f"""
    <div class="loader-wrap">
        <div class="orbit">
            <div class="orbit-core"></div>
            <div class="orbit-dot"></div>
            <div class="orbit-dot"></div>
            <div class="orbit-dot"></div>
        </div>
        <div class="loader-title">{title}</div>
        <div class="loader-sub">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)


# =========================================================
# CORE LOGIC — UNCHANGED FROM THE WORKING VERSION
# =========================================================

def get_db_name(interview_type):
    return questions_generate.DB_CODING if interview_type == "Coding" else questions_generate.DB_THEORY

def initialize_session():
    if "preload_box" not in st.session_state: st.session_state.preload_box = []
    if "stage" not in st.session_state: st.session_state.stage = "lobby"
    if "lobby_step" not in st.session_state: st.session_state.lobby_step = 1  
    if "selected_role" not in st.session_state: st.session_state.selected_role = "" 
    if "current_q" not in st.session_state: st.session_state.current_q = ""
    if "category" not in st.session_state: st.session_state.category = ""
    if "difficulty" not in st.session_state: st.session_state.difficulty = ""
    if "interview_type" not in st.session_state: st.session_state.interview_type = "" 
    if "start_time" not in st.session_state: st.session_state.start_time = 0
    if "seen_questions" not in st.session_state: st.session_state.seen_questions = []
    if "cheat_count" not in st.session_state: st.session_state.cheat_count = 0
    if "exam_answers" not in st.session_state: st.session_state.exam_answers = []
    if "final_results" not in st.session_state: st.session_state.final_results = []

def get_database_question(category, difficulty, seen_list, interview_type, job_role=""):
    try:
        conn = sqlite3.connect(get_db_name(interview_type))
        cursor = conn.cursor()

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

        if not row and job_role:
            fallback_conditions = ["category=?", "difficulty=?", "(job_role='' OR job_role IS NULL)"]
            fallback_params = [category, difficulty]
            if seen_list:
                placeholders = ",".join("?" for _ in seen_list)
                fallback_conditions.append(f"question NOT IN ({placeholders})")
                fallback_params += seen_list
            cursor.execute(f"SELECT question FROM interview_questions WHERE {' AND '.join(fallback_conditions)} ORDER BY RANDOM() LIMIT 1", fallback_params)
            row = cursor.fetchone()

        conn.close()
        return row[0] if row else None
    except Exception as e:
        print(f"🚨 [UI DB X-RAY ERROR] get_database_question failed: {e}")
        return f"SYSTEM ERROR: {str(e)}"

def _normalize_question(text):
    """X-RAY HELPER: strips the markdown prefix from current_q to produce compare-safe text."""
    return (text or "").replace("**Question:**", "").strip()

def get_evaluation_data_from_db(question_text):
    try:
        conn = sqlite3.connect(questions_generate.DB_CODING)
        cursor = conn.cursor()

        # Step 1: fast path — exact match
        cursor.execute("SELECT test_cases, ideal_answer, mandatory_keywords FROM interview_questions WHERE question=?", (question_text,))
        row = cursor.fetchone()

        # FIX: if the AI kept a '**Question:**' prefix when the question was saved
        # (which later gets stripped from current_q), the exact match would fail
        # and test_cases would silently come back []. Try a normalized fallback
        # so the real test cases aren't missed.
        if not row:
            print("🗄️ [UI DB X-RAY] No exact match found, trying the normalized fallback...")
            target = _normalize_question(question_text)
            cursor.execute("SELECT question, test_cases, ideal_answer, mandatory_keywords FROM interview_questions")
            for db_q, tcs, ideal, kws in cursor.fetchall():
                if _normalize_question(db_q) == target:
                    row = (tcs, ideal, kws)
                    print("🗄️ [UI DB X-RAY] ✅ Found a normalized match!")
                    break

        conn.close()
        if row:
            t_cases = json.loads(row[0]) if row[0] else []
            print(f"🗄️ [UI DB X-RAY] Fetched {len(t_cases)} test cases + ideal_answer for fallback.")
            return t_cases, row[1] or "", row[2] or ""
    except Exception as e:
        print(f"🚨 [UI DB X-RAY ERROR] get_evaluation_data_from_db failed: {e}")
    print("🗄️ [UI DB X-RAY] No evaluation data found in DB.")
    return [], "", ""

def fetch_question(category, difficulty, seen_list, interview_type, job_role):
    try:
        q = questions_generate.get_smart_question(category, difficulty, seen_list, interview_type, job_role)
    except Exception as e:
        print(f"🚨 [UI X-RAY ERROR] fetch_question API failed: {e}")
        q = None
    if not q or "SYSTEM ERROR" in q or q.startswith("TEST_COMPLETE") or q in seen_list:
        print("🔍 [UI X-RAY] Falling back to DB for question fetch...")
        q = get_database_question(category, difficulty, seen_list, interview_type, job_role)
    if q is None: return "TEST_COMPLETE: You have solved all available questions!"
    if q in seen_list: return "TEST_COMPLETE: No new unique questions!"
    return q.replace("**Question:**", "").strip()

def background_fetch(category, difficulty, seen_list, box, interview_type, job_role):
    add_script_run_ctx(threading.current_thread())
    if len(box) == 0:
        print("🔍 [UI X-RAY] Background fetch triggered...")
        q = fetch_question(category, difficulty, seen_list, interview_type, job_role)
        if q and not q.startswith("SYSTEM ERROR") and not q.startswith("TEST_COMPLETE"):
            box.append(q)
            print("🔍 [UI X-RAY] Background fetch successful. Question added to preload box.")
        else:
            print(f"🔍 [UI X-RAY] Background fetch did not return a usable question (got: '{q}'). Preload box will stay empty.")

def trigger_preload():
    print("🔍 [UI X-RAY] Starting thread for trigger_preload...")
    t = threading.Thread(target=background_fetch, args=(
        st.session_state.category, 
        st.session_state.difficulty, 
        st.session_state.seen_questions, 
        st.session_state.preload_box, 
        st.session_state.interview_type,
        st.session_state.selected_role
    ))
    add_script_run_ctx(t)
    t.start()

def save_question(question):
    if question and not question.startswith("TEST_COMPLETE") and not question.startswith("SYSTEM ERROR"):
        if question not in st.session_state.seen_questions:
            st.session_state.seen_questions.append(question)

def advance_to_next_question():
    if len(st.session_state.exam_answers) >= TOTAL_QUESTIONS:
        print("🔍 [UI X-RAY] All questions answered. Moving to processing stage.")
        st.session_state.stage = "processing"
        return
    if len(st.session_state.preload_box) > 0:
        new_q = st.session_state.preload_box.pop(0)
        print("🔍 [UI X-RAY] Popped new question from preload box.")
    else:
        print("🔍 [UI X-RAY] Preload box empty. Fetching new question synchronously...")
        new_q = fetch_question(st.session_state.category, st.session_state.difficulty, st.session_state.seen_questions, st.session_state.interview_type, st.session_state.selected_role)

    # FIX (this was the real bug): previously only "TEST_COMPLETE" was checked.
    # The "SYSTEM ERROR" check was missing, so if the DB crashed, the candidate
    # would see the raw error text displayed as if it were the next "question"!
    if new_q.startswith("TEST_COMPLETE") or new_q.startswith("SYSTEM ERROR"):
        if new_q.startswith("SYSTEM ERROR"):
            print(f"🚨 [UI X-RAY] Got a SYSTEM ERROR while fetching the next question: {new_q}")
            print("🔍 [UI X-RAY] Stopping the exam here — the report will only cover the answers collected so far.")
        else:
            print("🔍 [UI X-RAY] No new unique questions left, and none remain in the DB either.")
        st.session_state.stage = "processing"
    else:
        save_question(new_q)
        st.session_state.current_q = new_q
        st.session_state.start_time = time.time()
        st.session_state.stage = "interview"
        trigger_preload()

def lock_selectbox_typing():
    """Prevents typing/deleting inside Streamlit's selectbox search field
    (its hidden <input> normally supports type-to-filter). Keeps click-to-open
    and click-to-choose working exactly as before — only blocks manual keyboard
    edits, which was confusing candidates into thinking the role/skill name
    could be erased."""
    components.html("""
        <script>
            const doc = window.parent.document;
            function lockInputs() {
                doc.querySelectorAll('input[aria-autocomplete="list"]').forEach(inp => {
                    if (!inp.hasAttribute('readonly')) {
                        inp.setAttribute('readonly', 'readonly');
                    }
                });
            }
            lockInputs();
            if (!window.parent.__selectboxLockObserver) {
                const observer = new MutationObserver(lockInputs);
                observer.observe(doc.body, { childList: true, subtree: true });
                window.parent.__selectboxLockObserver = observer;
            }
        </script>
    """, height=0, width=0)

def main():
    st.set_page_config(page_title="AI Interview Trainer", page_icon="🤖", layout="centered")
    inject_theme()
    lock_selectbox_typing()
    st.markdown("<style>* { user-select: none !important; } textarea { user-select: text !important; }</style>", unsafe_allow_html=True)
    initialize_session()

    st.markdown(f"""
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.2rem;">
        <div style="font-family:'Sora',sans-serif;font-weight:800;font-size:20px;">
            Interview<span style="background:var(--gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">AI</span>
        </div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-secondary);letter-spacing:0.5px;">
            {st.session_state.stage.upper()}
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.title("🚀 AI Technical Interview Trainer")

    if st.session_state.stage == "lobby":
            components.html("<script>if(window.parent.myTimer) clearInterval(window.parent.myTimer); window.parent.examActive = false; if(window.parent.myMic) window.parent.myMic.stop();</script>", height=0, width=0)
            if st.session_state.lobby_step == 1:
                render_step_progress(1)
                st.subheader("🏢 Step 1: Select Your Target Job Role")
                selected_role = st.selectbox("Job Roles", list(ROLES_DATA.keys()))
                if st.button("Next ➡️", type="primary"):
                    print(f"🔍 [UI X-RAY] Lobby Step 1 -> Role selected: {selected_role}")
                    st.session_state.selected_role = selected_role
                    st.session_state.lobby_step = 2
                    st.rerun()
            elif st.session_state.lobby_step == 2:
                render_step_progress(2)
                st.subheader(f"🛠️ Step 2: Skills for {st.session_state.selected_role}")
                interview_type = st.radio("Format:", ["Theory Concepts (Verbal/Text)", "Coding / Practical"])
                if interview_type == "Theory Concepts (Verbal/Text)": available_skills, temp_type = ROLES_DATA[st.session_state.selected_role]["Theory"], "Theory"
                else: available_skills, temp_type = ROLES_DATA[st.session_state.selected_role]["Coding"], "Coding"
                selected_skill = st.selectbox("Select Skill:", available_skills)
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("⬅️ Back"):
                        st.session_state.lobby_step = 1
                        st.rerun()
                with col2:
                    if st.button("Next ➡️", type="primary"):
                        print(f"🔍 [UI X-RAY] Lobby Step 2 -> Type: {temp_type}, Skill: {selected_skill}")
                        st.session_state.interview_type = temp_type
                        st.session_state.category = selected_skill
                        st.session_state.lobby_step = 3
                        st.rerun()
            elif st.session_state.lobby_step == 3:
                render_step_progress(3)
                st.subheader("🔥 Step 3: Set Difficulty")
                st.info(f"**Target Role:** {st.session_state.selected_role}\n\n**Testing Skill:** {st.session_state.category} ({st.session_state.interview_type})")
                difficulty = st.selectbox("Choose Difficulty Level:", ["Foundation", "Applied", "Advanced", "Expert"])
                render_difficulty_timeline(difficulty)
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("⬅️ Back"):
                        st.session_state.lobby_step = 2
                        st.rerun()
                with col2:
                    if st.button("Next ➡️", type="primary"):
                        print(f"🔍 [UI X-RAY] Lobby Step 3 -> Difficulty: {difficulty}")
                        st.session_state.difficulty = difficulty
                        st.session_state.lobby_step = 4
                        st.rerun()
            elif st.session_state.lobby_step == 4:
                render_step_progress(4)
                st.subheader("📋 Step 4: Interview Rules & Guidelines")
                st.info(f"**Target Role:** {st.session_state.selected_role}\n\n**Testing Skill:** {st.session_state.category} ({st.session_state.interview_type})\n\n**Difficulty:** {st.session_state.difficulty}")
                render_rules_panel()
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("⬅️ Back"):
                        st.session_state.lobby_step = 3
                        st.rerun()
                with col2:
                    if st.button("Start Interview 🚀", type="primary"):
                        st.session_state.seen_questions = []
                        st.session_state.exam_answers = []
                        st.session_state.cheat_count = 0
                        st.session_state.preload_box = []  
                        
                        with st.spinner("Preparing your interview environment..."):
                            print("🔍 [UI X-RAY] Starting New Interview...")
                            print(f"🔍 [UI X-RAY] Role={st.session_state.selected_role}, Type={st.session_state.interview_type}, Skill={st.session_state.category}, Diff={st.session_state.difficulty}")
                            q = fetch_question(st.session_state.category, st.session_state.difficulty, st.session_state.seen_questions, st.session_state.interview_type, st.session_state.selected_role)
                            if q.startswith("TEST_COMPLETE") or q.startswith("SYSTEM ERROR"):
                                print(f"🚨 [UI X-RAY] Could not get even the first question: {q}")
                                st.error(q)
                            else:
                                save_question(q)
                                st.session_state.current_q = q
                                st.session_state.start_time = time.time()
                                st.session_state.stage = "interview"
                                trigger_preload()
                                st.rerun()

    elif st.session_state.stage == "interview":
        max_time = TIME_LIMITS.get(st.session_state.difficulty, 90)
        q_num = len(st.session_state.exam_answers)
        ring_circumference = round(2 * 3.14159265 * 28, 2)

        if st.button("CHEAT_BTN", key="cheat_btn"):
            st.session_state.exam_answers.append({"q": st.session_state.current_q, "a": "[NO ANSWER - TAB SWITCHED]", "time_taken": max_time, "event": "cheat"})
            st.session_state.cheat_count += 1
            st.session_state.stage = "processing" if len(st.session_state.exam_answers) >= TOTAL_QUESTIONS else "paused"
            st.rerun()

        if st.button("TIMEOUT_BTN", key="time_btn"):
            st.session_state.exam_answers.append({"q": st.session_state.current_q, "a": "[NO ANSWER PROVIDED]", "time_taken": max_time, "event": "timeout"})
            st.warning("⏰ Time's Up! Moving to next question...")
            time.sleep(1.2)
            advance_to_next_question()
            st.rerun()

        if st.button("AFK_BTN", key="afk_btn"):
            st.session_state.exam_answers.append({"q": st.session_state.current_q, "a": "[NO ANSWER PROVIDED]", "time_taken": max_time, "event": "timeout"})
            if len(st.session_state.exam_answers) >= TOTAL_QUESTIONS: st.session_state.stage = "processing"
            else: st.session_state.stage = "paused"
            st.rerun()

        unique_q_key = f"qTime_{q_num}_{int(st.session_state.start_time)}"

        components.html(f"""
            <script>
            const doc = window.parent.document;
            const parent = window.parent;
            parent.examActive = true;
            
            doc.addEventListener('copy', e => e.preventDefault());
            doc.addEventListener('paste', e => e.preventDefault());

            setInterval(() => {{
                ['CHEAT_BTN', 'TIMEOUT_BTN', 'AFK_BTN'].forEach(n => {{
                    let b = Array.from(doc.querySelectorAll('button')).find(btn => btn.innerText.includes(n));
                    if(b && b.style.display !== 'none') b.style.display = 'none';
                }});
            }}, 100);

            if (parent.cheatTimer) clearTimeout(parent.cheatTimer);
            doc.onvisibilitychange = () => {{
                if (doc.hidden && parent.examActive) {{
                    parent.cheatTimer = setTimeout(() => {{
                        let btn = Array.from(doc.querySelectorAll('button')).find(b => b.innerText.includes('CHEAT_BTN'));
                        if(btn) btn.click();
                    }}, 2000); 
                }} else {{ clearTimeout(parent.cheatTimer); }}
            }};

            let lastActive = Date.now();
            doc.onmousemove = () => lastActive = Date.now();
            doc.onkeydown = (e) => {{
                lastActive = Date.now();
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {{
                    e.preventDefault();
                    let sBtn = Array.from(doc.querySelectorAll('button')).find(b => b.innerText.includes('Save & Next') || b.innerText.includes('Final Submit Exam'));
                    if (sBtn) {{ if(parent.myTimer) clearInterval(parent.myTimer); parent.examActive = false; sBtn.click(); }}
                }}
            }};

            const qKey = "{unique_q_key}"; 
            if (parent.myTimer) clearInterval(parent.myTimer);
            
            parent.myTimer = setInterval(() => {{
                if(!parent.examActive) return;
                
                if(!parent.questionFullyTyped) {{
                    let ui = doc.getElementById('custom-clock');
                    if (ui) ui.innerText = {max_time}; 
                    return;
                }}
                
                if (!parent[qKey]) {{
                    parent[qKey] = Date.now() + ({max_time} * 1000);
                }}

                let left = Math.round((parent[qKey] - Date.now()) / 1000);
                let ui = doc.getElementById('custom-clock');
                if (ui) ui.innerText = left > 0 ? left : 0;

                let ring = doc.getElementById('timer-ring-fg');
                let ringWrap = doc.getElementById('timer-ring-wrap');
                if (ring) {{
                    let frac = Math.max(0, Math.min(1, left / {max_time}));
                    let circumference = {ring_circumference};
                    ring.style.strokeDashoffset = circumference * (1 - frac);
                    ring.style.stroke = frac > 0.5 ? '#4ECDC4' : (frac > 0.2 ? '#FFA94D' : '#FF6B6B');
                }}
                if (ringWrap) {{
                    if (left <= 15) ringWrap.classList.add('timer-critical');
                    else ringWrap.classList.remove('timer-critical');
                }}
                
                if (left <= 0) {{
                    clearInterval(parent.myTimer); parent.examActive = false;
                    if(Date.now() - lastActive > 20000) {{
                        let b = Array.from(doc.querySelectorAll('button')).find(x => x.innerText.includes('AFK_BTN'));
                        if(b) b.click();
                    }} else {{
                        let b = Array.from(doc.querySelectorAll('button')).find(x => x.innerText.includes('TIMEOUT_BTN'));
                        if(b) b.click();
                    }}
                }}
            }}, 1000);
            </script>
        """, height=1, width=1)

        st.subheader(f"Question {q_num + 1} of {TOTAL_QUESTIONS} | {st.session_state.category}")

        st.markdown(f"""
        <div class="timer-wrap">
          <div class="timer-ring-box" id="timer-ring-wrap">
            <svg width="64" height="64" viewBox="0 0 64 64">
              <circle class="timer-ring-bg" cx="32" cy="32" r="28" />
              <circle class="timer-ring-fg" id="timer-ring-fg" cx="32" cy="32" r="28"
                stroke-dasharray="{ring_circumference}" stroke-dashoffset="0" />
            </svg>
            <div class="timer-ring-text"><span id="custom-clock">{max_time}</span>s</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        clean_voice_q = st.session_state.current_q.replace('*', '').replace('#', '').replace('`', '')
        safe_q = json.dumps(clean_voice_q)
        safe_display_q = json.dumps(st.session_state.current_q)

        components.html(f"""
            <style>
                .ai-card {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    background: #151922;
                    padding: 16px 18px;
                    border-radius: 14px;
                    border: 1px solid rgba(255,255,255,0.08);
                    border-left: 3px solid #FF6B6B;
                    margin-bottom: 10px;
                    color: #F4F4F6;
                }}
                .ai-card-head {{
                    display: flex; align-items: center; justify-content: space-between;
                    border-bottom: 1px solid rgba(255,255,255,0.08);
                    padding-bottom: 8px; margin-bottom: 10px;
                }}
                .ai-card-head .left {{ display: flex; align-items: center; gap: 8px; }}
                .ai-wave {{ display: inline-flex; align-items: flex-end; gap: 3px; height: 14px; }}
                .ai-wave span {{ width: 3px; background: #FF6B6B; border-radius: 2px; animation: aiwave 1s ease-in-out infinite; }}
                .ai-wave span:nth-child(2) {{ animation-delay: 0.15s; }}
                .ai-wave span:nth-child(3) {{ animation-delay: 0.3s; }}
                @keyframes aiwave {{ 0%, 100% {{ height: 4px; }} 50% {{ height: 14px; }} }}
                #typewriter {{ min-height: 40px; max-height: 130px; overflow-y: auto; line-height: 1.6; color: #F4F4F6; font-size: 15px; }}
                .ai-mic-btn {{ border:none; background:none; cursor:pointer; font-size:18px; color:#8B8F9C; }}
            </style>
            <div class="ai-card">
                <div class="ai-card-head">
                    <div class="left">
                        <strong>🤖 AI Recruiter</strong>
                        <span class="ai-wave"><span></span><span></span><span></span></span>
                    </div>
                    <button class="ai-mic-btn" onclick="playVoice()"></button>
                </div>
                <div id="typewriter"></div>
            </div>
            <script>
                const displayText = {safe_display_q};
                const target = document.getElementById('typewriter');
                let i = 0; let isTyping = false;
                
                const qKey = "{unique_q_key}"; 
                
                if (window.parent[qKey]) {{
                    window.parent.questionFullyTyped = true;
                    target.innerHTML = displayText.replace(/\\n/g, '<br>');
                    target.scrollTop = target.scrollHeight;
                }} else {{
                    window.parent.questionFullyTyped = false;
                    playVoice();
                }}

                function type() {{
                    if(window.parent.questionFullyTyped) return;
                    if (i < displayText.length) {{
                        target.innerHTML += (displayText.charAt(i) === '\\n') ? '<br>' : displayText.charAt(i);
                        i++; 
                        setTimeout(type, 55); 
                        target.scrollTop = target.scrollHeight; 
                    }} else {{
                        window.parent.questionFullyTyped = true; 
                    }}
                }}
                
                function playVoice() {{
                    if (window.parent[qKey]) return; 
                    window.parent.speechSynthesis.cancel();
                    window.parent.aiSpeaking = true; 
                    const speech = new SpeechSynthesisUtterance({safe_q});
                    speech.lang = 'en-US';
                    speech.rate = 1.0;
                    
                    let voices = window.parent.speechSynthesis.getVoices();
                    let femaleVoice = voices.find(v => v.name.includes('Female') || v.name.includes('Zira') || v.name.includes('Samantha') || v.name.includes('Google UK English Female'));
                    if (femaleVoice) speech.voice = femaleVoice;
                    
                    speech.onstart = () => {{ if(!isTyping) {{ isTyping = true; type(); }} }};
                    speech.onend = () => {{ window.parent.aiSpeaking = false; }};
                    speech.onerror = () => {{ window.parent.aiSpeaking = false; }};
                    window.parent.speechSynthesis.speak(speech);
                }}
                
                if(window.parent.speechSynthesis.getVoices().length === 0) {{
                    window.parent.speechSynthesis.onvoiceschanged = () => {{ if(!window.parent[qKey]) playVoice(); }};
                }}
            </script>
        """, height=220)

        with st.sidebar:
            st.header("📝 Rough Pad")
            st.text_area("Scratchpad", height=400, key=f"rough_pad_{q_num}", label_visibility="collapsed")

        is_last_question = (q_num == TOTAL_QUESTIONS - 1)
        btn_label = "✅ Final Submit Exam" if is_last_question else "✅ Save & Next Question"

        if st.session_state.interview_type == "Coding":
            st.markdown(f'<div class="code-strip"><span>📝 solution.py</span><span>{st.session_state.category} · Python</span></div>', unsafe_allow_html=True)
            user_ans = st_ace(language="python", theme="monokai", key=f"ace_{q_num}", height=250, auto_update=True)
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("▶️ Run Code (Test)", use_container_width=True):
                    if not user_ans or not user_ans.strip(): st.warning("⚠️ Please write some code to run.")
                    else:
                        with st.spinner("Executing your code..."):
                            print("🔍 [UI X-RAY] User clicked 'Run Code'. Fetching execution data...")
                            db_test_cases, db_ideal, db_keys = get_evaluation_data_from_db(st.session_state.current_q)
                            if not db_test_cases: db_test_cases = [] 
                            is_safe, sec_msg = code_evaluate.security_scan(user_ans)
                            if not is_safe: st.error(f"🚨 {sec_msg}")
                            else:
                                print(f"🔍 [UI X-RAY] Running local execution for {st.session_state.category}...")
                                passed, pass_cnt, tot_cnt, msg = code_evaluate.run_test_cases(user_ans, db_test_cases, st.session_state.category)
                                if passed: st.success(f"✅ {pass_cnt}/{tot_cnt} Tests Passed!\n\n{msg}")
                                else: st.error(f"⚠️ Failed ({pass_cnt}/{tot_cnt}).\n\n{msg}")
            with col2:
                if st.button(btn_label, type="primary", use_container_width=True):
                    if not user_ans or not str(user_ans).strip(): st.error("⚠️ Answer cannot be empty!")
                    else:
                        st.session_state.exam_answers.append({"q": st.session_state.current_q, "a": user_ans, "time_taken": time.time() - st.session_state.start_time, "event": "normal"})
                        advance_to_next_question()
                        st.rerun()
        else:
            user_ans = st.text_area("Your Answer:", height=150, placeholder="Tap here and type your answer...", key=f"ans_box_{q_num}")
            # Auto-focus the answer box as soon as this question loads, so the
            # candidate can start typing immediately without clicking into it.
            components.html(f"""
                <script>
                    const doc = window.parent.document;
                    const focusFlag = "{unique_q_key}_focused";
                    if (!window.parent[focusFlag]) {{
                        window.parent[focusFlag] = true;
                        setTimeout(() => {{
                            const textAreas = Array.from(doc.querySelectorAll('textarea'));
                            const ansBox = textAreas[textAreas.length - 1];
                            if (ansBox) {{
                                ansBox.focus();
                                const len = ansBox.value.length;
                                ansBox.setSelectionRange(len, len);
                            }}
                        }}, 150);
                    }}
                </script>
            """, height=0, width=0)
            components.html("""
                            
                            <style>
                                #micBtn {
                                    transition: all 0.2s ease;
                                    display: inline-flex;
                                    align-items: center;
                                    justify-content: center;
                                    gap: 8px;
                                }
                                @keyframes pulse {
                                    0% { box-shadow: 0 0 0 0 rgba(255, 107, 107, 0.7); }
                                    70% { box-shadow: 0 0 0 15px rgba(255, 107, 107, 0); }
                                    100% { box-shadow: 0 0 0 0 rgba(255, 107, 107, 0); }
                                }
                                .mic-active {
                                    background-color: #ff6b6b !important;
                                    animation: pulse 1.5s infinite;
                                    transform: scale(1.05);
                                }
                                .mic-inactive {
                                    background: linear-gradient(135deg, #1A1E27, #151922) !important;
                                    border: 1px solid rgba(255,255,255,0.12) !important;
                                }
                            </style>

                            <div style="text-align: right; margin-top: -10px;">
                                <button id="micBtn" class="mic-inactive" style="color: white; border: none; padding: 10px 20px; border-radius: 10px; font-weight: bold; font-family: -apple-system, 'Segoe UI', sans-serif;">
                                    🎙️ Tap to Speak (or Hold Ctrl+Shift)
                                </button>
                            </div>

                            <script>
                                const parent = window.parent;
                                const doc = parent.document;
                                const micBtn = document.getElementById('micBtn');
                                const SpeechRec = parent.SpeechRecognition || parent.webkitSpeechRecognition;
                                
                                if (SpeechRec) {
                                    if(!parent.myMic) { 
                                        parent.myMic = new SpeechRec(); 
                                        parent.myMic.continuous = true; 
                                        parent.myMic.interimResults = true; 
                                        parent.myMic.lang = 'en-US'; 
                                    }
                                    
                                    parent.isHoldingKeys = false;
                                        // Tap-to-toggle support for mobile (no physical keyboard there,
                                        // so Ctrl+Shift can't work) — works on desktop too via click.
                                            let micOnByTap = false;
                                            micBtn.addEventListener('click', () => {
                                                if (parent.aiSpeaking) return;
                                                if (!micOnByTap) {
                                                    micOnByTap = true;
                                                    try { parent.myMic.start(); } catch(err) {}
                                                } else {
                                                    micOnByTap = false;
                                                    try { parent.myMic.stop(); } catch(err) {}
                                                }
                                            });

                                    parent.myMic.onstart = () => { 
                                        micBtn.classList.remove('mic-inactive');
                                        micBtn.classList.add('mic-active');
                                        micBtn.innerHTML = "🔴 Listening..."; 
                                        
                                        const textAreas = Array.from(doc.querySelectorAll('textarea'));
                                        const ansBox = textAreas[textAreas.length - 1];
                                        if(ansBox) {
                                            window.baseText = ansBox.value;
                                            if (window.baseText.length > 0 && !window.baseText.endsWith(" ")) {
                                                window.baseText += " ";
                                            }
                                        }
                                    };
                                    
                                    parent.myMic.onresult = (event) => {
                                        if (parent.aiSpeaking) return;
                                        let interimTranscript = '';
                                        let finalTranscript = '';

                                        for (let i = event.resultIndex; i < event.results.length; ++i) {
                                            if (event.results[i].isFinal) {
                                                finalTranscript += event.results[i][0].transcript.replace(/[.]/g, '') + ' ';
                                            } else {
                                                interimTranscript += event.results[i][0].transcript.replace(/[.]/g, '');
                                            }
                                        }
                                        
                                        const textAreas = Array.from(doc.querySelectorAll('textarea'));
                                        const ansBox = textAreas[textAreas.length - 1];
                                        
                                        if (ansBox) {
                                            window.baseText += finalTranscript;
                                            let displayText = window.baseText + interimTranscript;
                                            
                                            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                                            nativeSetter.call(ansBox, displayText);
                                            
                                            ansBox.dispatchEvent(new Event('input', { bubbles: true }));
                                            ansBox.dispatchEvent(new Event('change', { bubbles: true })); 
                                        }
                                    };
                                    
                                    parent.myMic.onend = () => { 
                                        parent.isHoldingKeys = false;
                                        micBtn.classList.remove('mic-active');
                                        micBtn.classList.add('mic-inactive');
                                        micBtn.innerHTML = "🎙️ Hold [Ctrl + Shift] to Speak"; 
                                    };

                                    doc.addEventListener('keydown', (e) => {
                                        if (e.ctrlKey && e.shiftKey && !parent.isHoldingKeys && !parent.aiSpeaking) {
                                            parent.isHoldingKeys = true;
                                            try { parent.myMic.start(); } catch(err) {}
                                        }
                                    });

                                    doc.addEventListener('keyup', (e) => {
                                        if ((!e.ctrlKey || !e.shiftKey) && parent.isHoldingKeys) {
                                            parent.isHoldingKeys = false;
                                            try { parent.myMic.stop(); } catch(err) {}
                                        }
                                    });

                                } else { 
                                    micBtn.innerHTML = "❌ Mic Not Supported"; 
                                }
                                
                                doc.addEventListener('click', (e) => {
                                    if(e.target.tagName === 'BUTTON' && (e.target.innerText.includes('Save') || e.target.innerText.includes('Submit'))) {
                                        if(parent.myMic) parent.myMic.stop();
                                    }
                                });
                            </script>
                        """, height=70)
            
            if st.button(btn_label, type="primary", use_container_width=True):
                if not user_ans or not str(user_ans).strip(): st.error("⚠️ Answer cannot be empty!")
                else:
                    st.session_state.exam_answers.append({"q": st.session_state.current_q, "a": user_ans, "time_taken": time.time() - st.session_state.start_time, "event": "normal"})
                    advance_to_next_question()
                    st.rerun()

    elif st.session_state.stage == "paused":
        components.html("<script>if (window.parent.myTimer) clearInterval(window.parent.myTimer); window.parent.examActive = false; if(window.parent.myMic) window.parent.myMic.stop();</script>", height=0, width=0)
        st.warning("⏸️ Warning: Tab switch or inactivity detected.")
        if st.button("▶️ Resume Test", key="resume_btn", type="primary", use_container_width=True):
            with st.spinner("Fetching next question..."): advance_to_next_question()
            st.rerun()

    elif st.session_state.stage == "processing":
        components.html("<script>if (window.parent.myTimer) clearInterval(window.parent.myTimer); window.parent.examActive = false; if(window.parent.myMic) window.parent.myMic.stop();</script>", height=0, width=0)
        render_loader("Scoring your performance...", "Reviewing responses and preparing feedback")
        
        current_type = st.session_state.interview_type 
        current_diff = st.session_state.difficulty 
        current_cat = st.session_state.category  
        
        def evaluate_single_answer(item):
            add_script_run_ctx(threading.current_thread())
            q_text, a_text, event = item["q"], item["a"] or "", item.get("event", "normal")
            if event == "cheat": return {"question": q_text, "answer": a_text, "status": "Wrong", "feedback": "Failed due to Cheating.", "points": -0.25}
            elif event == "timeout" and a_text in ("", "[NO ANSWER PROVIDED]"): return {"question": q_text, "answer": a_text, "status": "Incomplete", "feedback": "Time ran out.", "points": 0.0}
            
            try:
                if current_type == "Coding": 
                    print(f"🔍 [UI X-RAY] Processing final answer for: {q_text[:30]}...")
                    db_test_cases, db_ideal, db_keys = get_evaluation_data_from_db(q_text)
                    if not db_test_cases: db_test_cases = [] 
                    print(f"🔍 [UI X-RAY] Test cases available for final evaluation: {len(db_test_cases)}")
                    
                    print("🔍 [UI X-RAY] Calling code_evaluate.evaluate_candidate_code...")
                    res = code_evaluate.evaluate_candidate_code(q_text, a_text, db_test_cases, db_ideal, db_keys, current_diff, current_cat)
                    print(f"🔍 [UI X-RAY] Code Evaluator Response: {res}")
                    points = code_evaluate.calculate_code_score(res)
                else:
                    res = evaluate_answer.evaluate_candidate_answer(q_text, a_text, current_diff)
                    points = evaluate_answer.calculate_score(res)
            except Exception as e:
                # FIX: only the exception message was printed before, not the full
                # traceback — that made it hard to pin down where the crash actually happened.
                print(f"🚨 [UI X-RAY ERROR] Crash during evaluation for question '{q_text[:40]}...': {e}")
                traceback.print_exc()
                res = {"status": "Incomplete", "feedback": f"Error: {e}"}; points = 0.0
                
            return {"question": q_text, "answer": a_text, "status": res.get("status"), "feedback": res.get("overall_feedback") or res.get("feedback"), "points": points}

        print("🔍 [UI X-RAY] Starting Final Evaluation ThreadPool (max_workers=2 to prevent API crash)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            st.session_state.final_results = list(executor.map(evaluate_single_answer, st.session_state.exam_answers))
        
        print("🔍 [UI X-RAY] All answers evaluated successfully. Rendering results.")
        st.session_state.stage = "results"
        st.rerun()

    elif st.session_state.stage == "results":
        components.html("<script>if(window.parent.myTimer) clearInterval(window.parent.myTimer);</script>", height=0, width=0)
        st.title("🏆 Final Interview Report")
        total_score = max(0.0, sum([r["points"] for r in st.session_state.final_results]))
        print(f"📊 [RESULTS-X-RAY] Total Score: {total_score:.2f} / {len(st.session_state.final_results)} | Cheat count: {st.session_state.cheat_count}")
        render_score_ring(total_score, len(st.session_state.final_results))
        
        for idx, res in enumerate(st.session_state.final_results):
            with st.expander(f"Question {idx+1} | Result: {res['status']} | Score: {res['points']} marks", expanded=True):
                render_status_badge(res['status'])
                st.markdown(f"**📝 Question:** {res['question']}")
                
                st.markdown("**👤 Your Submission:**")
                if st.session_state.interview_type == "Coding": 
                    st.code(res['answer'], language='python')
                else: 
                    st.info(f"{res['answer']}")
                
                st.markdown("**🤖 AI Mentor Feedback:**")
                if res['status'] == "Correct": 
                    st.success(f"🌟 {res['feedback']}")
                elif res['status'] == "Partial": 
                    st.warning(f"👍 {res['feedback']}")
                else: 
                    st.error(f"💡 {res['feedback']}")
                    
        if st.button("Return to Lobby", type="primary", use_container_width=True):
            st.session_state.preload_box = []  
            st.session_state.lobby_step = 1    
            st.session_state.stage = "lobby"
            st.rerun()

if __name__ == "__main__":
    main()