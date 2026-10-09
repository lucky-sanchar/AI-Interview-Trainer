"""
resume_engine.py  -  drop this next to your Streamlit app.

What it does
  1. extract_text()        PDF (path / bytes / Streamlit upload) -> text
  2. analyze_resume()      general ATS-readiness score (no JD needed) + tips + skills + projects
  3. match_jd()            resume vs JD (or vs a role) -> match % + missing skills/keywords
  4. generate_questions()  company / scenario / project-based interview questions
                           (LLM if API key works, otherwise offline fallback -> demo never fails)

Deps: pdfplumber, requests   (no scikit-learn, no spaCy, no NLTK)
Keys: read from config.py (GEN_GEMINI_KEYS, GEN_GROQ_KEYS)
"""
import io
import json
import math
import os
import re
from collections import Counter

from config import GEN_GEMINI_KEYS

try:
    from config import GEN_GROQ_KEYS
except Exception:  # pragma: no cover
    GEN_GROQ_KEYS = []

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None
try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

RESUME_CATEGORY = "Resume Based"


# ----------------------------------------------------------------------------
# 1. PDF -> text
# ----------------------------------------------------------------------------
def extract_text(source):
    """source = file path | bytes | file-like | Streamlit UploadedFile."""
    if pdfplumber is None:
        raise RuntimeError("pdfplumber missing: pip install pdfplumber")
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    elif hasattr(source, "getvalue"):  # UploadedFile / BytesIO
        source = io.BytesIO(source.getvalue())
    parts = []
    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


# ----------------------------------------------------------------------------
# 2. Skills / sections knowledge
# ----------------------------------------------------------------------------
SKILLS = {
    "python": ["python"], "java": ["java"], "c++": ["c++"],
    "javascript": ["javascript", "js", "es6"], "typescript": ["typescript"],
    "html": ["html", "html5"], "css": ["css", "css3"],
    "react": ["react", "reactjs", "react js"],
    "node.js": ["node", "nodejs", "node js"],
    "django": ["django"], "flask": ["flask"], "fastapi": ["fastapi"],
    "streamlit": ["streamlit"],
    "sql": ["sql"], "mysql": ["mysql"], "postgresql": ["postgresql", "postgres"],
    "mongodb": ["mongodb", "mongo"], "sqlite": ["sqlite"],
    "rest api": ["rest api", "rest apis", "restful", "restful api", "restful apis"],
    "git": ["git", "github", "gitlab"],
    "docker": ["docker"], "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services"], "azure": ["azure"],
    "gcp": ["gcp", "google cloud"], "linux": ["linux", "ubuntu"],
    "agile": ["agile", "scrum"],
    "data structures": ["data structures", "dsa", "algorithms"],
    "oop": ["oop", "oops", "object oriented", "object-oriented"],
    "machine learning": ["machine learning", "ml"],
    "deep learning": ["deep learning", "neural network", "neural networks", "cnn", "lstm"],
    "nlp": ["nlp", "natural language processing"],
    "tensorflow": ["tensorflow", "keras"], "pytorch": ["pytorch"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "pandas": ["pandas"], "numpy": ["numpy"], "opencv": ["opencv"],
    "data visualization": ["matplotlib", "seaborn", "plotly", "power bi", "tableau"],
    "excel": ["excel"], "statistics": ["statistics", "statistical"],
    "llm": ["llm", "llms", "langchain", "openai", "gemini", "rag"],
    "tailwind": ["tailwind", "tailwindcss"], "bootstrap": ["bootstrap"],
    "authentication": ["jwt", "oauth", "authentication"],
    "unit testing": ["pytest", "unittest", "jest"],
    "ci/cd": ["ci/cd", "github actions", "jenkins"],
}

_SKILL_RX = {}
for _canon, _aliases in SKILLS.items():
    _all = sorted(set(_aliases + [_canon]), key=len, reverse=True)
    _SKILL_RX[_canon] = re.compile(
        r"(?<![a-z0-9+#.])(?:" + "|".join(re.escape(a) for a in _all) + r")(?![a-z0-9+#])"
    )

ROLE_SKILLS = {
    "software engineer": ["python", "java", "data structures", "oop", "sql", "git", "rest api", "linux"],
    "backend developer": ["python", "django", "flask", "fastapi", "sql", "postgresql", "rest api", "docker", "git", "authentication"],
    "frontend developer": ["javascript", "react", "html", "css", "typescript", "git", "rest api", "tailwind"],
    "full stack developer": ["javascript", "react", "node.js", "sql", "mongodb", "rest api", "git", "docker"],
    "data analyst": ["sql", "python", "pandas", "excel", "data visualization", "statistics", "numpy"],
    "data scientist": ["python", "machine learning", "statistics", "pandas", "numpy", "scikit-learn", "sql", "data visualization"],
    "ml engineer": ["python", "machine learning", "deep learning", "tensorflow", "pytorch", "scikit-learn", "docker", "git", "sql"],
    "ai engineer": ["python", "machine learning", "nlp", "llm", "deep learning", "fastapi", "docker", "git"],
}

STOP = set("""a an the and or of to in for with on at by from as is are be been being this that these those it its
you your we our they their will would should can could may might must shall have has had do does did not no but if
then than so such into over under about looking strong ideal candidate experience experienced knowledge good great
plus huge etc able ability work working team role job required requirements preferred responsibilities skills skill
years year including include using use used also well new know""".split())

_HEADERS = {
    "education": ["education", "academic", "academics", "qualification", "qualifications"],
    "skills": ["skills", "technical skills", "tech stack", "technologies", "key skills"],
    "projects": ["projects", "personal projects", "academic projects", "project work"],
    "experience": ["experience", "internship", "internships", "work experience", "achievements",
                   "hackathon", "hackathons", "certifications", "certificates", "positions of responsibility"],
    "other": ["summary", "objective", "profile", "links", "languages", "interests", "hobbies",
              "contact", "declaration", "references", "about me", "career objective"],
}


def role_skills(role):
    r = (role or "").lower().strip()
    if r in ROLE_SKILLS:
        return ROLE_SKILLS[r]
    if "ml" in r.split() or "machine" in r:
        return ROLE_SKILLS["ml engineer"]
    if "data sci" in r:
        return ROLE_SKILLS["data scientist"]
    if "analyst" in r:
        return ROLE_SKILLS["data analyst"]
    if "front" in r:
        return ROLE_SKILLS["frontend developer"]
    if "back" in r:
        return ROLE_SKILLS["backend developer"]
    if "full" in r:
        return ROLE_SKILLS["full stack developer"]
    if r.startswith("ai") or " ai" in r:
        return ROLE_SKILLS["ai engineer"]
    return ROLE_SKILLS["software engineer"]


def find_skills(text):
    low = (text or "").lower()
    return {c for c, rx in _SKILL_RX.items() if rx.search(low)}


def _header_of(line):
    cleaned = re.sub(r"[^a-z& ]", "", line.lower()).strip()
    if not cleaned or len(cleaned) > 35:
        return None
    for key, names in _HEADERS.items():
        if cleaned in names:
            return key
    return None


def split_sections(text):
    sections, current = {}, None
    for line in (text or "").splitlines():
        h = _header_of(line)
        if h:
            current = h
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line.strip())
    return sections


# ----------------------------------------------------------------------------
# 3. General ATS-readiness score (no JD needed)
# ----------------------------------------------------------------------------
def analyze_resume(text):
    """Returns dict: ok, score, breakdown, tips, skills, projects_text, words."""
    if not text or len(text.split()) < 40:
        return {"ok": False,
                "error": "Could not read text from this PDF (scanned image or empty). "
                         "Please upload a text-based PDF."}
    low = text.lower()
    sections = split_sections(text)
    words = len(low.split())
    tips, bd = [], {}

    has_email = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", low))
    has_phone = bool(re.search(r"\+?\d[\d\s\-]{8,}\d", low))
    bd["Contact info"] = (5 if has_email else 0) + (5 if has_phone else 0)
    if not has_email:
        tips.append("Add a professional email address at the top.")
    if not has_phone:
        tips.append("Add a phone number at the top.")

    sec_pts = 0
    for key, label in [("education", "Education"), ("skills", "Skills"),
                       ("projects", "Projects"), ("experience", "Experience / Internships / Hackathons")]:
        if key in sections:
            sec_pts += 10
        else:
            tips.append("Add a clear '%s' section heading." % label)
    bd["Sections"] = sec_pts

    skills = find_skills(text)
    bd["Skills coverage"] = min(len(skills), 10) * 2
    if len(skills) < 8:
        tips.append("List more relevant technical skills (you have %d detected)." % len(skills))

    impact = len(re.findall(r"\d+\s?%", text)) + len(re.findall(
        r"\b\d+\+?\s*(?:users|students|records|requests|models|projects|participants|teams|ms|seconds|images|rows|features)\b",
        low))
    bd["Quantified impact"] = min(impact, 5) * 3
    if impact < 3:
        tips.append("Add numbers to project bullets (e.g. 'improved accuracy by 12%', 'handled 500+ records').")

    if 250 <= words <= 800:
        bd["Length"] = 15
    elif 120 <= words < 250 or 800 < words <= 1100:
        bd["Length"] = 8
        tips.append("Resume length is off (%d words). Aim for 250-800 words, ideally 1 page." % words)
    else:
        bd["Length"] = 3
        tips.append("Resume length is far from ideal (%d words)." % words)

    proj_text = "\n".join(sections.get("projects", []))[:1800]
    if not proj_text.strip():
        tips.append("Describe 2-3 projects with tech stack and your contribution.")

    return {"ok": True, "score": min(sum(bd.values()), 100), "breakdown": bd,
            "tips": tips, "skills": sorted(skills), "projects_text": proj_text, "words": words}


# ----------------------------------------------------------------------------
# 4. Resume vs JD / role match
# ----------------------------------------------------------------------------
def _stem(w):
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _tokens(text):
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    return [_stem(w) for w in cleaned.split() if len(w) > 2 and w not in STOP]


def _cosine(a, b):
    ca, cb = Counter(a), Counter(b)
    dot = sum(ca[w] * cb[w] for w in ca if w in cb)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


def jd_from_role(role):
    return "%s role requiring %s." % (role, ", ".join(role_skills(role)))


def match_jd(resume_text, jd_text):
    """Skill coverage (50%) + keyword coverage (30%) + cosine (20%). Pure Python."""
    if not resume_text.strip() or not jd_text.strip():
        return {"score": 0.0, "matched_skills": [], "missing_skills": [], "missing_keywords": []}

    jd_sk, rs_sk = find_skills(jd_text), find_skills(resume_text)
    matched, missing = sorted(jd_sk & rs_sk), sorted(jd_sk - rs_sk)

    jd_tok, rs_tok = _tokens(jd_text), _tokens(resume_text)
    jd_set, rs_set = set(jd_tok), set(rs_tok)
    kw_cov = len(jd_set & rs_set) / len(jd_set) if jd_set else 0.0
    cos = _cosine(rs_tok, jd_tok)

    if jd_sk:
        skill_cov = len(matched) / len(jd_sk)
        score = 0.5 * skill_cov + 0.3 * kw_cov + 0.2 * cos
    else:
        score = 0.7 * kw_cov + 0.3 * cos

    jd_freq = Counter(jd_tok)
    miss_kw = [k for k, _ in jd_freq.most_common() if k not in rs_set
               and not any(k in s for s in missing)][:6]
    return {"score": round(score * 100, 1), "matched_skills": matched,
            "missing_skills": missing, "missing_keywords": miss_kw}


# ----------------------------------------------------------------------------
# 5. Interview questions (LLM + offline fallback)
# ----------------------------------------------------------------------------
def call_llm(prompt, timeout=45):
    """Tries every Gemini key, then every Groq key. Returns plain text."""
    if requests is None:
        raise RuntimeError("requests missing")
    errors = []
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    for key in list(GEN_GEMINI_KEYS or []):
        if not key or str(key).startswith("YOUR_"):
            continue
        try:
            r = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model,
                params={"key": key}, timeout=timeout,
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}})
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            errors.append("gemini: %s" % e)
    for key in list(GEN_GROQ_KEYS or []):
        if not key or str(key).startswith("YOUR_"):
            continue
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions", timeout=timeout,
                headers={"Authorization": "Bearer %s" % key, "Content-Type": "application/json"},
                json={"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.7, "response_format": {"type": "json_object"}, "max_tokens": 4096})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            errors.append("groq: %s" % e)
    raise RuntimeError("No LLM available: " + "; ".join(errors)[:300])


def _parse_json(raw):
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    s, e = raw.find("{"), raw.rfind("}")
    return json.loads(raw[s:e + 1])


def _kw_str(v):
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x).strip() for x in v if str(x).strip())
    return str(v or "").strip()


def _clean_q(q):
    return re.sub(r"\s+", " ", str(q or "").replace("**Question:**", "")).strip()


def _norm_items(items):
    out = []
    for it in items or []:
        if isinstance(it, str):
            out.append({"question": _clean_q(it), "hint": "", "ideal_answer": "", "keywords": ""})
        elif isinstance(it, dict) and it.get("question"):
            out.append({"question": _clean_q(it["question"]),
                        "hint": str(it.get("hint", "")).strip(),
                        "ideal_answer": str(it.get("ideal_answer", "")).strip(),
                        "keywords": _kw_str(it.get("keywords", ""))})
    return [o for o in out if o["question"]]


_Q_WORDS = {"what", "how", "why", "when", "where", "which", "explain", "describe", "would", "does", "your", "have", "this", "that", "solve", "hardest", "problem", "should"}


def _fill_references(items):
    """Guarantee every question has an ideal_answer + keywords (so a reference always exists)."""
    for it in items:
        if not it.get("ideal_answer"):
            it["ideal_answer"] = (
                "A strong answer explains the concept clearly, gives a concrete example from the candidate's "
                "own work, and mentions trade-offs and specific tools or steps."
                + (" Interviewer looks for: %s" % it["hint"] if it.get("hint") else ""))
        if not it.get("keywords"):
            toks = []
            for t in _tokens(it["question"]):
                if len(t) > 3 and t not in toks and t not in _Q_WORDS:
                    toks.append(t)
            it["keywords"] = ", ".join(toks[:4]) or "example, implementation, trade-offs"
    return items


def _register_references(res, company, role):
    """Saves every question + ideal answer into the DB (via evaluate_answer) so scoring and the
    results screen can always find the reference answer."""
    try:
        import evaluate_answer
    except Exception as e:
        print("[RESUME] evaluate_answer import failed, skipping DB register: %s" % e)
        return
    for key in ("company_questions", "scenario_questions", "project_questions"):
        for it in res.get(key, []):
            try:
                evaluate_answer.register_reference(it["question"], it["ideal_answer"], it["keywords"],
                                                   category=RESUME_CATEGORY, difficulty="Applied",
                                                   job_role="Resume")
            except Exception as e:
                print("[RESUME] register_reference failed: %s" % e)


def _offline_questions(company, role, skills, missing, projects_text):
    sk = list(skills)[:5] or role_skills(role)[:5]
    company_q = [{"question": "Why do you want to join %s as a %s?" % (company, role),
                  "hint": "Genuine motivation + research about the company."}]
    for s in sk[:4]:
        company_q.append({"question": "Explain %s and where you have used it. What would you do differently now?" % s,
                          "hint": "Depth of hands-on knowledge."})
    scenario_q = [
        {"question": "Your feature works locally but fails in production. How do you debug it?",
         "hint": "Logs, environment differences, systematic isolation."},
        {"question": "A page/API suddenly becomes 5x slower. How do you find the bottleneck?",
         "hint": "Profiling, DB queries, caching, measuring before fixing."},
        {"question": "Two teammates disagree on the tech stack. How do you resolve it?",
         "hint": "Communication and trade-off thinking."},
    ]
    if missing:
        scenario_q.append({"question": "This role needs %s but it's new to you. How would you learn it in 2 weeks?" % missing[0],
                           "hint": "Learning plan and honesty about gaps."})
    lines = [l.strip(" -•*\t") for l in (projects_text or "").splitlines()]
    cands = [l for l in lines if 8 <= len(l) <= 90]
    # prefer title-like lines ("Name - description", "Name | stack", "Name: ...")
    titles = ([l for l in cands if re.search(r"\s[-|:]\s|:", l) and not re.match(r"(?i)built|developed|used|implemented|designed|created", l)]
              or cands)[:4]
    titles = [re.split(r"\s[-|:]\s|:", t)[0].strip() for t in titles]
    templates = ["In '%s', what was the hardest problem and how did you solve it?",
                 "In '%s', why did you choose that tech stack over alternatives?",
                 "How would you scale '%s' to 100x more users?",
                 "What would you improve in '%s' if you had one more month?"]
    project_q = [{"question": templates[i % 4] % t, "hint": "Ownership and technical depth."}
                 for i, t in enumerate(titles)]
    if not project_q:
        project_q = [{"question": "Walk me through your best project end to end.",
                      "hint": "Problem, design, your contribution, result."}]
    return {"company_questions": company_q, "scenario_questions": scenario_q, "project_questions": project_q}


def generate_questions(company, role, analysis, match=None):
    """analysis = analyze_resume() output, match = match_jd() output (optional).
    Always returns questions; 'source' tells whether AI or offline fallback was used."""
    skills = analysis.get("skills", [])
    missing = (match or {}).get("missing_skills", [])
    projects = analysis.get("projects_text", "")
    prompt = (
        "You are a senior interviewer preparing a mock interview for a fresher/student candidate.\n"
        "Target company: %s\nTarget role: %s\nCandidate skills: %s\n"
        "Skills the role needs but the resume lacks: %s\n"
        "Candidate's projects (from resume):\n%s\n\n"
        "Return ONLY valid JSON with exactly these keys:\n"
        '"company_questions": 5 questions that %s (or similar companies for this role) is commonly reported to ask, '
        "mixing technical and HR.\n"
        '"scenario_questions": 3 realistic work scenarios for this role (debugging, scaling, teamwork, trade-offs).\n'
        '"project_questions": 4 deep-dive questions about the candidate\'s ACTUAL projects above; name the project in each.\n'
        'Each item: {"question": "...", "hint": "one line on what the interviewer looks for", '
        '"ideal_answer": "a concise 2-3 sentence model answer", "keywords": "3-5 comma-separated key terms a good answer contains"}.\n'
        "If no projects are listed, base project_questions on the candidate's listed skills instead.\n"
        "Do not claim the questions are official or verified. Keep difficulty fresher-appropriate."
    ) % (company, role, ", ".join(skills) or "not listed", ", ".join(missing) or "none",
         projects or "(none found)", company)

    res = None
    for _ in range(2):
        try:
            data = _parse_json(call_llm(prompt))
            cand = {k: _norm_items(data.get(k)) for k in
                    ("company_questions", "scenario_questions", "project_questions")}
            if all(cand.values()):
                cand["source"] = "ai"
                res = cand
                break
        except Exception as e:
            print("[RESUME] LLM attempt failed: %s" % e)
            continue
    if res is None:
        res = _offline_questions(company, role, skills, missing, projects)
        res["source"] = "offline"
    for k in ("company_questions", "scenario_questions", "project_questions"):
        res[k] = _norm_items(res.get(k))
        _fill_references(res[k])
    _register_references(res, company, role)
    return res


# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r"C:\my_resume.pdf"
    if not os.path.exists(path):
        raise SystemExit("File not found: %s" % path)
    a = analyze_resume(extract_text(path))
    print(a if not a["ok"] else "ATS readiness: %s/100\nTips: %s" % (a["score"], a["tips"]))
    if a["ok"]:
        m = match_jd(extract_text(path), jd_from_role("Backend Developer"))
        print("Backend Developer match:", m)
        print(json.dumps(generate_questions("TCS", "Backend Developer", a, m), indent=2))
