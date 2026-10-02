# 🚀 AI Interview Trainer

An AI-powered technical interview practice platform built with Streamlit. It simulates a real technical interview — generating fresh questions on the fly, evaluating answers with AI, and producing a detailed performance report — so candidates can practice before the real thing.

---

## ✨ Features

- **Role-based practice** — choose a target job role (e.g. Software Engineer, Data Scientist, Web Developer) and the interview is tailored to it.
- **Two interview formats:**
  - **Theory mode** — conceptual/verbal questions, answered via text or voice (speech-to-text).
  - **Coding mode** — live coding questions in an in-browser code editor with syntax highlighting.
- **Difficulty levels** — Foundation, Applied, Advanced, Expert.
- **AI question generation** — questions are generated dynamically by AI (not hardcoded), with a 3-engine fallback chain (Groq → Gemini → Cohere) so the app keeps working even if one provider is down or rate-limited.
- **Automatic test-case validation** — for coding questions, AI-generated test cases are verified against the AI's own reference solution before being stored, so candidates are never scored against a wrong expected output.
- **Local sandboxed code execution** — candidate code runs in an isolated subprocess with a security scan (blocks file access, network calls, `eval`/`exec`, etc.) before any test is run.
- **AI-powered evaluation** — both theory and code answers are reviewed by AI for correctness, with a offline NLP/keyword-similarity fallback if all AI engines are unavailable.
- **Anti-cheat monitoring** — detects tab-switching, copy/paste, and prolonged inactivity during the live interview.
- **Live interview UX** — circular countdown timer, typewriter-animated AI question delivery with text-to-speech, a scratchpad sidebar, and a push-to-talk microphone for voice answers.
- **Results dashboard** — an animated score ring, per-question breakdown with color-coded status (Correct / Partial / Wrong / Incomplete), and AI mentor feedback for every answer.
- **Offline-friendly** — previously generated questions are cached in a local SQLite database and reused if there's no internet connection.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend / App framework | [Streamlit](https://streamlit.io/) |
| Code editor widget | [streamlit-ace](https://github.com/okld/streamlit-ace) |
| Database | SQLite (separate DBs for theory & coding questions) |
| AI providers | [Groq](https://groq.com/), [Google Gemini](https://ai.google.dev/), [Cohere](https://cohere.com/) |
| Code execution | Python `subprocess` sandbox with pattern-based security scanning |
| Config / secrets | `python-dotenv` (local) + Streamlit Secrets (cloud deployment) |

---

## 📂 Project Structure

```
.
├── interview_ui.py          # Main Streamlit app — UI, session state, exam flow
├── questions_generate.py    # AI question generation (3-engine fallback) + DB storage
├── evaluate_answer.py       # Theory answer evaluation (AI + NLP fallback)
├── code_evaluate.py         # Code security scan, sandbox execution, AI code review
├── roles_db.py              # Job roles and their associated skills/topics
├── config.py                # Centralized API key loading (.env / Streamlit Secrets)
├── requirements.txt         # Python dependencies
├── .env                     # Local API keys (NOT committed — see below)
├── theory_questions.db      # SQLite cache of theory questions (auto-created)
└── coding_questions.db      # SQLite cache of coding questions (auto-created)
```

---

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

### 4. Configure API keys
Create a `.env` file in the project root with your API keys:

```env
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

> Multiple keys per provider can be comma-separated — the app rotates through them if one fails or hits a rate limit.

### 5. Run the app
```bash
python -m streamlit run interview_ui.py
```

The app will open at `http://localhost:8501`.

---

## ☁️ Deployment

This app is ready to deploy on [Streamlit Community Cloud](https://share.streamlit.io) for free:

1. Push this repository to GitHub (the `.env` file is excluded via `.gitignore` — never commit real API keys).
2. Create a new app on Streamlit Cloud and point it to `interview_ui.py`.
3. In the app's **Secrets** panel, add the same keys from your `.env` file in TOML format.
4. Deploy — you'll get a public link that works on any device.

---

## 🔒 Security Notes

- Candidate-submitted code never runs with file, network, or system access — it's blocked by a pattern-based security scan before execution.
- API keys are never hardcoded; they're loaded exclusively from environment variables / Streamlit Secrets.
- `.env` is excluded from version control via `.gitignore`.

---

## 📄 License

This project was built as an academic/minor project. Feel free to adapt it for your own learning.