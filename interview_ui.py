import streamlit as st
import sqlite3
import time
import json
import threading
import traceback
from streamlit.runtime.scriptrunner import add_script_run_ctx
import streamlit.components.v1 as components
from streamlit_ace import st_ace

from roles_db import ROLES_DATA
import questions_generate
import evaluate_answer
import code_evaluate
import resume_engine  

TIME_LIMITS = {"Foundation": 90, "Applied": 180, "Advanced": 300, "Expert": 420}
TOTAL_QUESTIONS = 5

# =========================================================
# UI THEME & PRESENTATION HELPERS
# =========================================================

def inject_theme():
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

    [data-testid="stSelectbox"] > div > div,
    [data-testid="stTextArea"] textarea,
    [data-testid="stTextInput"] > div > div {
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

    [data-testid="stAlert"] {
        border-radius: 12px !important;
        font-family: 'Inter', sans-serif !important;
        border: 1px solid var(--border) !important;
    }

    [data-testid="stSidebar"] {
        background: var(--surface) !important;
        border-right: 1px solid var(--border) !important;
    }

    .step-track { display: flex; align-items: center; gap: 8px; margin-bottom: 1.8rem; }
    .step-seg { height: 4px; flex: 1; border-radius: 999px; background: var(--border); overflow: hidden; }
    .step-seg.filled { background: var(--gradient); }
    .step-label { font-size: 13px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace; white-space: nowrap; }

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

    .loader-wrap { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 4rem 0; gap: 1rem; }
    .orbit { position: relative; width: 90px; height: 90px; }
    .orbit-core { position: absolute; inset: 0; margin: auto; width: 14px; height: 14px; border-radius: 50%; background: var(--gradient); }
    .orbit-dot { position: absolute; width: 10px; height: 10px; border-radius: 50%; background: var(--coral); top: 0; left: 50%; transform-origin: 5px 45px; animation: orbitSpin 1.6s linear infinite; }
    .orbit-dot:nth-child(2) { background: var(--amber); animation-duration: 2.1s; }
    .orbit-dot:nth-child(3) { background: var(--teal); animation-duration: 2.6s; animation-direction: reverse; }
    @keyframes orbitSpin { from { transform: rotate(0deg) translateY(0) rotate(0deg); } to { transform: rotate(360deg) translateY(0) rotate(-360deg); } }
    .loader-title { font-family: 'Sora', sans-serif; font-weight: 700; font-size: 19px; }
    .loader-sub { color: var(--text-secondary); font-size: 14px; }

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
    .rules-list li .rule-text { flex: 1; }
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
    segs = "".join(f'<div class="step-seg {"filled" if i < current_step else ""}"></div>' for i in range(total_steps))
    st.markdown(f'<div class="step-track"><span class="step-label">Step {current_step} of {total_steps}</span>{segs}</div>', unsafe_allow_html=True)

def render_difficulty_timeline(selected_difficulty):
    levels = ["Foundation", "Applied", "Advanced", "Expert"]
    nodes = ""
    for i, lvl in enumerate(levels, start=1):
        active = (lvl == selected_difficulty)
        circle_cls = "diff-circle active" if active else "diff-circle"
        name_cls = "diff-name active" if active else "diff-name"
        nodes += f'<div class="diff-node"><div class="{circle_cls}">{i:02d}</div><div class="{name_cls}">{lvl}</div></div>'
    st.markdown(f'<div class="diff-track">{nodes}</div>', unsafe_allow_html=True)

def render_status_badge(status):
    cls_map = {"Correct": "correct", "Partial": "partial", "Wrong": "wrong", "Incomplete": "incomplete"}
    icon_map = {"Correct": "✓", "Partial": "◐", "Wrong": "✕", "Incomplete": "–"}
    cls = cls_map.get(status, "incomplete")
    icon = icon_map.get(status, "–")
    st.markdown(f'<span class="status-pill {cls}">{icon} {status}</span>', unsafe_allow_html=True)

def render_rules_panel():
    html = """
    <div class="rules-card">
        <div class="rules-section">
            <div class="rules-section-title">🧭 How this interview works</div>
            <ul class="rules-list">
                <li><span class="bullet-icon coral">1</span><span class="rule-text">You'll be asked <b>5 questions</b> in total, generated fresh by AI based on your selected role, skill and difficulty.</span></li>
                <li><span class="bullet-icon coral">2</span><span class="rule-text">Depending on the format you chose, questions are either <b>Theory</b> (answer by typing or speaking) or <b>Coding</b> (write and run real code).</span></li>
                <li><span class="bullet-icon coral">3</span><span class="rule-text">Once you move to the next question, you <b>cannot go back</b>.</span></li>
            </ul>
        </div>
        <div class="rules-section">
            <div class="rules-section-title">🎛️ Operating the interview</div>
            <ul class="rules-list">
                <li><span class="bullet-icon teal">1</span><span class="rule-text">The AI reads each question aloud automatically.</span></li>
                <li><span class="bullet-icon teal">2</span><span class="rule-text">For Theory questions: type your answer, or use the <b>mic button</b>.</span></li>
                <li><span class="bullet-icon teal">3</span><span class="rule-text">Click <b>Save & Next Question</b> when you're ready to move on.</span></li>
            </ul>
        </div>
        <div class="rules-section">
            <div class="rules-section-title">⏱️ Timing & Conduct</div>
            <ul class="rules-list">
                <li><span class="bullet-icon amber">1</span><span class="rule-text">Each question has a <b>countdown timer</b>.</span></li>
                <li><span class="bullet-icon coral">2</span><span class="rule-text">Switching tabs or minimizing the window is detected as a cheating attempt.</span></li>
            </ul>
        </div>
    </div>
    """
    html = "\n".join(line.strip() for line in html.strip("\n").split("\n"))
    st.markdown(html, unsafe_allow_html=True)

def render_score_ring(score, max_score):
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

import html as _html
import re as _re

def _project_titles(projects_text, limit=5):
    lines = [l.strip(" -•*\t") for l in (projects_text or "").splitlines()]
    cands = [l for l in lines if 8 <= len(l) <= 90]
    titled = [l for l in cands
              if _re.search(r"\s[-|:–]\s|:", l)
              and not _re.match(r"(?i)(built|developed|used|implemented|designed|created|worked|integrated)", l)]
    titles = [_re.split(r"\s[-|:–]\s|:", t)[0].strip() for t in (titled or cands)]
    seen, out = set(), []
    for t in titles:
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:limit]

def _chips(items, color_rgb, color_hex):
    return "".join(
        f'<span style="display:inline-block;margin:4px 6px 4px 0;padding:5px 12px;border-radius:999px;'
        f'background:rgba({color_rgb},0.12);color:{color_hex};border:1px solid rgba({color_rgb},0.35);'
        f'font-size:12px;font-weight:600;">{_html.escape(str(i))}</span>'
        for i in items
    )

def render_resume_summary(analysis):
    st.markdown("### 📊 Your Resume Report")
    render_score_ring(analysis["score"], 100)

    skills = analysis.get("skills", [])
    st.markdown(f"**🛠️ Skills detected ({len(skills)}):**")
    if skills:
        st.markdown(_chips(skills, "78,205,196", "#4ECDC4"), unsafe_allow_html=True)
    else:
        st.caption("No known technical skills detected. Add a clear Skills section.")

    projects = _project_titles(analysis.get("projects_text", ""))
    st.markdown(f"**🚀 Projects detected ({len(projects)}):**")
    if projects:
        st.markdown(_chips(projects, "255,169,77", "#FFA94D"), unsafe_allow_html=True)
    else:
        st.caption("No projects section detected. Project-based questions will be skipped.")

    with st.expander("Score breakdown"):
        for k, v in analysis.get("breakdown", {}).items():
            st.write(f"- {k}: **{v}**")
    if analysis.get("tips"):
        with st.expander("💡 How to improve your resume"):
            for t in analysis["tips"][:6]:
                st.write(f"- {t}")

# =========================================================
# CORE LOGIC
# =========================================================

def get_db_name(interview_type):
    return questions_generate.DB_CODING if interview_type == "Coding" else questions_generate.DB_THEORY

def initialize_session():
    if "preload_box" not in st.session_state: st.session_state.preload_box = []
    if "stage" not in st.session_state: st.session_state.stage = "lobby"
    
    if "lobby_step" not in st.session_state: st.session_state.lobby_step = 0  
    
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
    
    if "use_resume_questions" not in st.session_state: st.session_state.use_resume_questions = False
    if "custom_resume_questions" not in st.session_state: st.session_state.custom_resume_questions = []
    if "custom_q_ideals" not in st.session_state: st.session_state.custom_q_ideals = {}  

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
        return f"SYSTEM ERROR: {str(e)}"

def _normalize_question(text):
    return (text or "").replace("**Question:**", "").strip()

def get_evaluation_data_from_db(question_text):
    try:
        conn = sqlite3.connect(questions_generate.DB_CODING)
        cursor = conn.cursor()
        cursor.execute("SELECT test_cases, ideal_answer, mandatory_keywords FROM interview_questions WHERE question=?", (question_text,))
        row = cursor.fetchone()

        if not row:
            target = _normalize_question(question_text)
            cursor.execute("SELECT question, test_cases, ideal_answer, mandatory_keywords FROM interview_questions")
            for db_q, tcs, ideal, kws in cursor.fetchall():
                if _normalize_question(db_q) == target:
                    row = (tcs, ideal, kws)
                    break

        conn.close()
        if row:
            t_cases = json.loads(row[0]) if row[0] else []
            return t_cases, row[1] or "", row[2] or ""
    except Exception:
        pass
    return [], "", ""

def get_coding_ideal_answer(question_text):
    import re
    try:
        q_raw = (question_text or "").replace("**Question:**", "").strip()
        key = " ".join(q_raw.lower().split())
        conn = sqlite3.connect("coding_questions.db")
        cur = conn.cursor()
        cur.execute("SELECT ideal_answer FROM interview_questions WHERE question=? OR question=?", (q_raw, question_text))
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT question, ideal_answer FROM interview_questions")
            for dq, ia in cur.fetchall():
                if " ".join((dq or "").replace("**Question:**", "").lower().split()) == key:
                    row = (ia,)
                    break
        conn.close()
        if row and row[0]:
            return re.sub(r"^```(?:python)?\s*|\s*```$", "", str(row[0]).strip()).strip()
    except Exception as e:
        print(f"🚨 [UI X-RAY ERROR] get_coding_ideal_answer failed: {e}")
    return ""

def fetch_question(category, difficulty, seen_list, interview_type, job_role):
    try:
        q = questions_generate.get_smart_question(category, difficulty, seen_list, interview_type, job_role)
    except Exception:
        q = None
    if not q or "SYSTEM ERROR" in q or q.startswith("TEST_COMPLETE") or q in seen_list:
        q = get_database_question(category, difficulty, seen_list, interview_type, job_role)
    if q is None: return "TEST_COMPLETE: You have solved all available questions!"
    if q in seen_list: return "TEST_COMPLETE: No new unique questions!"
    return q.replace("**Question:**", "").strip()

def background_fetch(category, difficulty, seen_list, box, interview_type, job_role):
    add_script_run_ctx(threading.current_thread())
    if len(box) == 0:
        q = fetch_question(category, difficulty, seen_list, interview_type, job_role)
        if q and not q.startswith("SYSTEM ERROR") and not q.startswith("TEST_COMPLETE"):
            box.append(q)

def trigger_preload():
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
        st.session_state.stage = "processing"
        return
        
    if st.session_state.get("use_resume_questions"):
        if len(st.session_state.custom_resume_questions) > 0:
            new_q = st.session_state.custom_resume_questions.pop(0)
        else:
            new_q = "TEST_COMPLETE: You have solved all available questions!"
            
        if new_q.startswith("TEST_COMPLETE"):
            st.session_state.stage = "processing"
        else:
            save_question(new_q)
            st.session_state.current_q = new_q
            st.session_state.start_time = time.time()
            st.session_state.stage = "interview"
        return

    if len(st.session_state.preload_box) > 0:
        new_q = st.session_state.preload_box.pop(0)
    else:
        new_q = fetch_question(st.session_state.category, st.session_state.difficulty, st.session_state.seen_questions, st.session_state.interview_type, st.session_state.selected_role)

    if new_q.startswith("TEST_COMPLETE") or new_q.startswith("SYSTEM ERROR"):
        st.session_state.stage = "processing"
    else:
        save_question(new_q)
        st.session_state.current_q = new_q
        st.session_state.start_time = time.time()
        st.session_state.stage = "interview"
        trigger_preload()

def lock_selectbox_typing():
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
            
            if st.session_state.lobby_step == 0:
                st.subheader("📄 Pre-Screening: AI Resume Parsing (Optional)")
                st.info("Upload your resume to generate a personalized mock interview based on your ACTUAL skills and projects!")
                
                uploaded_file = st.file_uploader("Upload Resume (PDF format)", type=["pdf"])
                
                if uploaded_file is not None:
                    if "resume_analysis" not in st.session_state:
                        with st.spinner("Analyzing Resume Structure & Skills..."):
                            resume_text = resume_engine.extract_text(uploaded_file)
                            st.session_state.resume_text = resume_text
                            st.session_state.resume_analysis = resume_engine.analyze_resume(resume_text)
                    
                    analysis = st.session_state.resume_analysis
                    
                    if analysis["ok"]:
                        render_resume_summary(analysis)
                        
                        st.markdown("### 🎯 Setup Your Personalized Interview")
                        col1, col2 = st.columns(2)
                        with col1:
                            target_company = st.text_input("Target Company (e.g., Google, TCS):", "Google")
                        with col2:
                            target_role = st.text_input("Target Role (e.g., Backend Developer):", "Software Engineer")
                        
                        if st.button("🚀 Start Personalized Interview", type="primary", use_container_width=True):
                            with st.spinner("Crafting customized questions based on your resume..."):
                                match = resume_engine.match_jd(st.session_state.resume_text, resume_engine.jd_from_role(target_role))
                                qs_data = resume_engine.generate_questions(target_company, target_role, analysis, match)
                                
                                pool = []
                                for q in qs_data.get("company_questions", []): pool.append(q)
                                for q in qs_data.get("scenario_questions", []): pool.append(q)
                                
                                if analysis.get("projects_text", "").strip():
                                    for q in qs_data.get("project_questions", []): pool.append(q)
                                
                                if len(pool) < TOTAL_QUESTIONS:
                                    pool.extend([{"question": "Could you elaborate on your general technical experience?", "hint": "Candidate should confidently explain their past roles and tech stack."}] * (TOTAL_QUESTIONS - len(pool)))
                                
                                # MEMORY SAVE HACK: Dict me direct hints save kardi
                                st.session_state.custom_q_ideals = {p["question"]: (p.get("ideal_answer") or p.get("hint") or "No reference available.") for p in pool[:TOTAL_QUESTIONS]}
                                st.session_state.custom_resume_questions = [p["question"] for p in pool[:TOTAL_QUESTIONS]]
                                st.session_state.use_resume_questions = True
                                
                                st.session_state.interview_type = "Theory Concepts (Verbal/Text)"
                                st.session_state.difficulty = "Applied"
                                st.session_state.category = target_role
                                st.session_state.exam_answers = []
                                st.session_state.seen_questions = []
                                
                                st.session_state.current_q = st.session_state.custom_resume_questions.pop(0)
                                st.session_state.start_time = time.time()
                                st.session_state.stage = "interview"
                                st.rerun()
                    else:
                        st.error(analysis["error"])
                
                st.markdown("---")
                if st.button("Skip to Standard Interview ➡️", use_container_width=True):
                    st.session_state.lobby_step = 1
                    st.rerun()

            elif st.session_state.lobby_step == 1:
                render_step_progress(1)
                st.subheader("🏢 Step 1: Select Your Target Job Role")
                selected_role = st.selectbox("Job Roles", list(ROLES_DATA.keys()))
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("⬅️ Back"):
                        st.session_state.lobby_step = 0
                        st.rerun()
                with col2:
                    if st.button("Next ➡️", type="primary"):
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
                        st.session_state.use_resume_questions = False
                        st.session_state.seen_questions = []
                        st.session_state.exam_answers = []
                        st.session_state.cheat_count = 0
                        st.session_state.preload_box = []  
                        
                        with st.spinner("Preparing your interview environment..."):
                            q = fetch_question(st.session_state.category, st.session_state.difficulty, st.session_state.seen_questions, st.session_state.interview_type, st.session_state.selected_role)
                            if q.startswith("TEST_COMPLETE") or q.startswith("SYSTEM ERROR"):
                                st.error(q)
                            else:
                                save_question(q)
                                st.session_state.current_q = q
                                st.session_state.start_time = time.time()
                                st.session_state.stage = "interview"
                                trigger_preload()
                                st.rerun()

    elif st.session_state.stage == "interview":
        max_time = TIME_LIMITS.get(st.session_state.difficulty, 180) 
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
                            db_test_cases, db_ideal, db_keys = get_evaluation_data_from_db(st.session_state.current_q)
                            if not db_test_cases: db_test_cases = [] 
                            is_safe, sec_msg = code_evaluate.security_scan(user_ans)
                            if not is_safe: st.error(f"🚨 {sec_msg}")
                            else:
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
            q_text, a_text, event = item["q"], item["a"] or "", item.get("event", "normal")
            status, feedback, points = "Incomplete", "Error occurred.", 0.0

            if event == "cheat": 
                status, feedback, points = "Wrong", "Failed due to Cheating.", -0.25
            elif event == "timeout" and a_text in ("", "[NO ANSWER PROVIDED]"): 
                status, feedback, points = "Incomplete", "Time ran out.", 0.0
            else:
                try:
                    if current_type == "Coding": 
                        db_test_cases, db_ideal, db_keys = get_evaluation_data_from_db(q_text)
                        if not db_test_cases: db_test_cases = [] 
                        res = code_evaluate.evaluate_candidate_code(q_text, a_text, db_test_cases, db_ideal, db_keys, current_diff, current_cat)
                        points = code_evaluate.calculate_code_score(res)
                        status = res.get("status", "Incomplete")
                        feedback = res.get("overall_feedback") or res.get("feedback", "")
                    else:
                        res = evaluate_answer.evaluate_candidate_answer(q_text, a_text, current_diff)
                        points = evaluate_answer.calculate_score(res)
                        status = res.get("status", "Incomplete")
                        feedback = res.get("overall_feedback") or res.get("feedback", "")
                except Exception as e:
                    traceback.print_exc()
                    feedback = f"Error: {e}"

            # 🚀 MEMORY / DB SAFE IDEAL ANSWER LOGIC
            ideal_ans = ""
            q_clean = q_text.replace("**Question:**", "").strip()

            if current_type == "Coding":
                ideal_ans = get_coding_ideal_answer(q_clean)
            else:
                try:
                    _ref = evaluate_answer.get_reference(q_clean)
                    if _ref.get("ideal_answer"):
                        ideal_ans = _ref["ideal_answer"]
                except Exception:
                    pass

                if not ideal_ans and st.session_state.get("use_resume_questions"):
                    hint = st.session_state.custom_q_ideals.get(q_text) or st.session_state.custom_q_ideals.get(q_clean)
                    if hint:
                        ideal_ans = hint

                if not ideal_ans:
                    try:
                        db_ideal = questions_generate.get_ideal_answer_from_db(q_clean, current_type)
                        if db_ideal and db_ideal.strip().startswith("{"):
                            try:
                                parsed = json.loads(db_ideal)
                                if isinstance(parsed, dict):
                                    ideal_ans = parsed.get("approach", parsed.get("ideal_answer", parsed.get("unidirectional_alternative", str(parsed))))
                            except Exception:
                                ideal_ans = db_ideal
                        else:
                            ideal_ans = db_ideal
                    except Exception:
                        pass

            if not ideal_ans or not str(ideal_ans).strip():
                ideal_ans = "Reference answer is not available for this question."
                    
            return {
                "question": q_text, 
                "answer": a_text, 
                "status": status, 
                "feedback": feedback, 
                "points": points,
                "ideal_answer": ideal_ans 
            }

        # 🚀 NORMAL SYNCHRONOUS LOOP: No Threading! Fixes the "missing ScriptRunContext" permanently
        results = []
        for ans in st.session_state.exam_answers:
            results.append(evaluate_single_answer(ans))
        st.session_state.final_results = results
        
        st.session_state.stage = "results"
        st.rerun()

    elif st.session_state.stage == "results":
        components.html("<script>if(window.parent.myTimer) clearInterval(window.parent.myTimer);</script>", height=0, width=0)
        st.title("🏆 Final Interview Report")
        
        total_score = max(0.0, sum([r["points"] for r in st.session_state.final_results]))
        render_score_ring(total_score, len(st.session_state.final_results))
        
        show_ideal = st.session_state.get("show_ideal_answers", False)
        if st.button("Hide Ideal Answers" if show_ideal else "💡 Show Ideal Answers", use_container_width=True):
            st.session_state.show_ideal_answers = not show_ideal
            st.rerun()
            
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
                
                if st.session_state.get("show_ideal_answers", False):
                    st.markdown("**✅ Ideal Answer (reference):**")
                    if st.session_state.interview_type == "Coding":
                        st.code(res['ideal_answer'], language='python')
                    else:
                        st.info(res['ideal_answer'])
                    st.caption("AI-generated reference answer. Other valid approaches may exist.")
                    
        if st.button("Return to Lobby", type="primary", use_container_width=True):
            st.session_state.preload_box = []
            st.session_state.show_ideal_answers = False  
            st.session_state.lobby_step = 0    
            st.session_state.stage = "lobby"
            if "resume_analysis" in st.session_state:
                del st.session_state["resume_analysis"]
            st.rerun()

if __name__ == "__main__":
    main()