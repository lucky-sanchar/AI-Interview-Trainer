# 🚀 AI Interview Trainer

An AI-powered technical interview practice platform built with Streamlit. It simulates a real technical interview: generating fresh questions on the fly, evaluating answers with AI, and producing a detailed performance report, so candidates can practice before the real thing.

New: upload your resume to get an ATS score and a mock interview personalized to your own skills and projects.

## ✨ Features

- **Role-based practice**: choose a target job role (e.g. Software Engineer, Data Scientist, Web Developer) and the interview is tailored to it.
- **Two interview formats:**
  - **Theory mode**: conceptual/verbal questions, answered via text or voice (speech-to-text).
  - **Coding mode**: live coding questions in an in-browser code editor with syntax highlighting.
- **Difficulty levels**: Foundation, Applied, Advanced, Expert.
- **📄 Resume Analyzer (optional)**: upload a PDF resume before the interview and get:
  - an **ATS readiness score out of 100** (contact info, sections, skills, quantified impact, length) with a score breakdown and improvement tips
  - the **skills and projects detected** in your resume
  - a **role match %** against your target role or a pasted job description
- **🎯 Personalized interview**: enter a target company and role, and the interview uses company-style questions, real-world scenario questions, and deep-dive questions about the projects on your resume. It runs in the same timed, anti-cheat interview engine as the standard mode.
- **AI question generation**: questions are generated dynamically by AI (not hardcoded), with a multi-engine fallback chain (Groq → Gemini → Cohere) so the app keeps working even if one provider is down or rate-limited.
- **Automatic test-case validation**: for coding questions, AI-generated test cases are verified against the AI's own reference solution before being stored, so candidates are never scored against a wrong expected output.
- **Local sandboxed code execution**: candidate code runs in an isolated subprocess with a security scan (blocks file access, network calls, eval/exec, etc.) before any test is run.
- **AI-powered evaluation**: both theory and code answers are reviewed by AI for correctness, with an offline NLP/keyword-similarity fallback if all AI engines are unavailable.
- **Ideal reference answers**: the results screen has a "Show Ideal Answers" toggle for every question, in both theory and coding modes. Reference answers for resume-based questions are generated together with the questions and stored in the local database.
- **Anti-cheat monitoring**: detects tab-switching, copy/paste, and prolonged inactivity during the live interview.
- **Live interview UX**: circular countdown timer, typewriter-animated AI question delivery with text-to-speech, a scratchpad sidebar, and a push-to-talk microphone for voice answers.
- **Results dashboard**: an animated score ring, per-question breakdown with color-coded status (Correct / Partial / Wrong / Incomplete), and AI mentor feedback for every answer.
- **Offline-friendly**: previously generated questions are cached in a local SQLite database and reused if there is no internet connection. Resume questions also fall back to built-in practice questions if every AI provider is unreachable.

## 🧮 How the resume scoring works

The resume analyzer is written in pure Python. It needs no scikit-learn, no spaCy, and no paid API for scoring.

- **ATS readiness (0-100):** contact info (10) + sections (40) + skills coverage (20) + quantified impact (15) + length (15).
- **Role / JD match %:** skill coverage (50%) + keyword coverage (30%) + cosine similarity (20%).
- Only **text-based PDFs** are supported. Scanned image resumes cannot be read.
- Interview question generation (not scoring) uses the same AI providers as the rest of the app.

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend / App framework | Streamlit |
| Code editor widget | streamlit-ace |
| Database | SQLite (separate DBs for theory & coding questions) |
| AI providers | Groq, Google Gemini, Cohere |
| Code execution | Python subprocess sandbox with pattern-based security scanning |
| Resume parsing | pdfplumber + pure-Python scoring |
| Config / secrets | python-dotenv (local) + Streamlit Secrets (cloud deployment) |

## 📂 Project Structure

```
.
├── interview_ui.py         # Main Streamlit app: UI, session state, exam flow, resume report
├── resume_engine.py        # Resume PDF parsing, ATS score, role match, resume-based question generation
├── questions_generate.py   # AI question generation (multi-engine fallback) + DB storage
├── evaluate_answer.py      # Theory answer evaluation (AI + NLP fallback) + reference answer storage
├── code_evaluate.py        # Code security scan, sandbox execution, AI code review
├── roles_db.py             # Job roles and their associated skills/topics
├── config.py               # Centralized API key loading (.env / Streamlit Secrets)
├── requirements.txt        # Python dependencies
├── .env                    # Local API keys (NOT committed, see below)
├── theory_questions.db     # SQLite cache of theory questions (auto-created)
└── coding_questions.db     # SQLite cache of coding questions (auto-created)
```

## ⚙️ Setup & Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd my_ai_interview_trainer
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Make sure `requirements.txt` includes `pdfplumber` and `requests` (used by the resume analyzer) along with the existing packages.

### 4. Configure API keys

Create a `.env` file in the project root with your API keys:

```
GEN_GROQ_KEYS=gsk_xxxxx,gsk_yyyyy
GEN_GEMINI_KEYS=AIzaxxxxx,AIzayyyyy
GEN_COHERE_KEY=xxxxxxxxxx
EVAL_GROQ_KEYS=gsk_xxxxx
EVAL_GEMINI_KEYS=AIzaxxxxx
EVAL_COHERE_KEY=xxxxxxxxxx
CODE_GROQ_KEYS=gsk_xxxxx
CODE_GEMINI_KEYS=AIzaxxxxx
CODE_COHERE_KEY=xxxxxxxxxx
```

Multiple keys per provider can be comma-separated. The app rotates through them if one fails or hits a rate limit. The resume question generator uses the `GEN_*` keys, and reference answers use the `EVAL_*` keys.

### 5. Run the app

```bash
python -m streamlit run interview_ui.py
```

The app will open at `http://localhost:8501`.

## 🧭 How to use

1. **(Optional)** On the first screen, upload your resume PDF to see your ATS score, detected skills, and detected projects.
2. Enter your target company and role, then start the personalized interview. Or click **Skip to Standard Interview** to pick a role, format, and difficulty yourself.
3. Answer five timed questions by typing, speaking, or coding.
4. Review your score, AI feedback, and ideal answers on the results screen.

## ☁️ Deployment

This app is ready to deploy on Streamlit Community Cloud for free:

1. Push this repository to GitHub (the `.env` file is excluded via `.gitignore`. Never commit real API keys).
2. Create a new app on Streamlit Cloud and point it to `interview_ui.py`.
3. In the app's **Secrets** panel, add the same keys from your `.env` file in TOML format.
4. Deploy. You'll get a public link that works on any device.

## 🔒 Security Notes

- Candidate-submitted code never runs with file, network, or system access. It is blocked by a pattern-based security scan before execution.
- API keys are never hardcoded; they're loaded exclusively from environment variables / Streamlit Secrets.
- `.env` is excluded from version control via `.gitignore`.
- Uploaded resumes are processed in memory for the session and are not saved to disk by the app.

## 📄 License

This project was built as an academic/minor project. Feel free to adapt it for your own learning.
