import os
from dotenv import load_dotenv

# Explicitly load .env from the same directory as config.py
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
env_loaded = load_dotenv(dotenv_path=env_path, override=True)

# =========================================================
# 0. STREAMLIT CLOUD SUPPORT
# On Streamlit Community Cloud there is no .env file — keys are instead
# entered into the app's "Secrets" panel, which Streamlit exposes via
# st.secrets. Here we copy any matching secrets into os.environ so every
# get_keys_list()/get_single_key() call below works unchanged, whether
# the app is running locally (.env) or deployed (Streamlit Secrets).
# =========================================================
_SECRET_KEY_NAMES = [
    "GEN_GROQ_KEYS", "GEN_GEMINI_KEYS", "GEN_COHERE_KEY",
    "EVAL_GROQ_KEYS", "EVAL_GEMINI_KEYS", "EVAL_COHERE_KEY",
    "CODE_GROQ_KEYS", "CODE_GEMINI_KEYS", "CODE_COHERE_KEY",
]

try:
    import streamlit as st
    for _key in _SECRET_KEY_NAMES:
        if _key in st.secrets:
            os.environ[_key] = str(st.secrets[_key])
    print("ℹ️ [CONFIG X-RAY] Streamlit Secrets detected and merged into the environment.")
except Exception as e:
    # Raised locally when there's no secrets.toml / no Streamlit Cloud secrets
    # configured — that's expected for a local run, .env simply takes over.
    print(f"ℹ️ [CONFIG X-RAY] No Streamlit Secrets found (normal for a local run): {e}")


def get_keys_list(env_name):
    raw_val = os.getenv(env_name, "")
    # Clean any accidental quotes or whitespace around keys
    return [k.strip().strip('"').strip("'") for k in raw_val.split(",") if k.strip()]


def get_single_key(env_name):
    raw_val = os.getenv(env_name, "")
    return raw_val.strip().strip('"').strip("'")


# =========================================================
# 1. For questions_generate.py
# =========================================================
GEN_GROQ_KEYS = get_keys_list("GEN_GROQ_KEYS")
GEN_GEMINI_KEYS = get_keys_list("GEN_GEMINI_KEYS")
GEN_COHERE_KEY = get_single_key("GEN_COHERE_KEY")

# Aliases so questions_generate.py works with both naming styles
GROQ_KEYS = GEN_GROQ_KEYS
GEMINI_KEYS = GEN_GEMINI_KEYS
COHERE_API_KEY = GEN_COHERE_KEY

# =========================================================
# 2. For evaluate_answer.py
# =========================================================
EVAL_GROQ_KEYS = get_keys_list("EVAL_GROQ_KEYS")
EVAL_GEMINI_KEYS = get_keys_list("EVAL_GEMINI_KEYS")
EVAL_COHERE_KEY = get_single_key("EVAL_COHERE_KEY")
EVAL_COHERE_KEYS = EVAL_COHERE_KEY  # Safe alias

# =========================================================
# 3. For code_evaluate.py
# =========================================================
CODE_GROQ_KEYS = get_keys_list("CODE_GROQ_KEYS")
CODE_GEMINI_KEYS = get_keys_list("CODE_GEMINI_KEYS")
CODE_COHERE_KEY = get_single_key("CODE_COHERE_KEY")
CODE_COHERE_KEYS = CODE_COHERE_KEY  # Safe alias


# =========================================================
# 4. X-RAY KEY DIAGNOSTICS (Runs when you execute: python config.py)
# =========================================================
def _mask_key(k):
    if not k:
        return "❌ EMPTY"
    return f"{k[:6]}...{k[-4:]} (len={len(k)})"


if __name__ == "__main__":
    print("\n" + "="*55)
    print("🔐 [CONFIG X-RAY] CHECKING .ENV & API KEYS")
    print("="*55)
    print(f"📂 Looking for .env at: {env_path}")
    print(f"✅ .env File Found & Loaded: {env_loaded}\n")

    pools = {
        "GEN_GROQ_KEYS (Expected: gsk_...)": GEN_GROQ_KEYS,
        "GEN_GEMINI_KEYS (Expected: AIzaSy...)": GEN_GEMINI_KEYS,
        "GEN_COHERE_KEY": [GEN_COHERE_KEY] if GEN_COHERE_KEY else [],
        "EVAL_GROQ_KEYS (Expected: gsk_...)": EVAL_GROQ_KEYS,
        "EVAL_GEMINI_KEYS (Expected: AIzaSy...)": EVAL_GEMINI_KEYS,
        "EVAL_COHERE_KEY": [EVAL_COHERE_KEY] if EVAL_COHERE_KEY else [],
        "CODE_GROQ_KEYS (Expected: gsk_...)": CODE_GROQ_KEYS,
        "CODE_GEMINI_KEYS (Expected: AIzaSy...)": CODE_GEMINI_KEYS,
        "CODE_COHERE_KEY": [CODE_COHERE_KEY] if CODE_COHERE_KEY else [],
    }

    for name, key_list in pools.items():
        if not key_list:
            print(f" ❌ {name}: 0 keys loaded!")
        else:
            masked = ", ".join(_mask_key(k) for k in key_list)
            print(f" 🟢 {name}: {len(key_list)} key(s) -> [{masked}]")
    print("="*55 + "\n")