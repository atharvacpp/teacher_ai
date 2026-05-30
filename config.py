"""
config.py — Centralised configuration for the ExplainAI backend.

Loads environment variables, initialises shared clients, and exports
constants used across routers and services.
"""

import os

from dotenv import load_dotenv
from huggingface_hub import InferenceClient

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

load_dotenv()

# Hugging Face
HF_API_KEY: str | None = os.getenv("HUGGINGFACE_API_KEY")
if not HF_API_KEY:
    raise RuntimeError(
        "HUGGINGFACE_API_KEY is not set. "
        "Please add it to your .env file before starting the server."
    )

# ---------------------------------------------------------------------------
# Model IDs
# ---------------------------------------------------------------------------

CHAT_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
ASR_MODEL_ID  = "openai/whisper-large-v3-turbo"

# ---------------------------------------------------------------------------
# Ollama (local VLM — Phase 3)
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_VLM_MODEL = os.getenv("OLLAMA_VLM_MODEL", "llava")

# ---------------------------------------------------------------------------
# Retry settings (for cold-starting HF models)
# ---------------------------------------------------------------------------

MAX_RETRIES         = 3
RETRY_DELAY_SECONDS = 5

# ---------------------------------------------------------------------------
# Shared Clients
# ---------------------------------------------------------------------------

hf_client = InferenceClient(api_key=HF_API_KEY)
