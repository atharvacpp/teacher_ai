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

# Groq
GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY is not set. Pipeline C will be disabled.")

# Pinecone
PINECONE_API_KEY: str | None = os.getenv("PINECONE_API_KEY")
if not PINECONE_API_KEY or PINECONE_API_KEY == "your-pinecone-api-key-here":
    print("WARNING: PINECONE_API_KEY is not set. Self-RAG retrieval will fall back to web search.")
    PINECONE_API_KEY = None

PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "teacher-ai")

# ---------------------------------------------------------------------------
# Model IDs
# ---------------------------------------------------------------------------

CHAT_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"    # text reasoning (cloud)
ASR_MODEL_ID  = "base"  # speech recognition (local faster-whisper)
DEBUGGER_MODEL = "deepseek-coder-v2"          # autonomous debugging (local)
OLLAMA_BASE_URL = "http://localhost:11434"    # local ollama instance

# Vision (LLaVA) is handled locally via Ollama — see services/llava_vision.py

# ---------------------------------------------------------------------------
# Retry settings (for cold-starting HF models)
# ---------------------------------------------------------------------------

MAX_RETRIES         = 3
RETRY_DELAY_SECONDS = 5

# ---------------------------------------------------------------------------
# Shared Clients
# ---------------------------------------------------------------------------

hf_client = InferenceClient(api_key=HF_API_KEY)
