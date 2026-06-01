# 🧠 ExplainAI — Multimodal AI Teaching Platform

> **Phase 5** · Text, Voice, Multimodal inference, Video analysis, and sandboxed Code Execution powered by Qwen 2.5, Ollama LLaVA, Distil-Whisper, LangGraph, and a Docker MCP sandbox.

---

## 📁 Project Structure

```
teacher_ai/
│
├── main.py                        # FastAPI app shell (CORS, lifespan, router registration)
├── config.py                      # Env vars, model IDs, shared clients
├── schemas.py                     # Pydantic request/response models
├── requirements.txt               # Python dependencies
├── .env                           # Environment variables (API keys — git-ignored)
│
├── routers/                       # FastAPI APIRouter modules (thin HTTP layer)
│   ├── chat.py                    # POST /chat — text conversation
│   ├── upload.py                  # POST /upload — image & PDF analysis
│   ├── execute.py                 # POST /execute-code — sandboxed code execution
│   ├── video.py                   # POST /video/upload — video analysis
│   └── voice.py                   # POST /transcribe — speech-to-text
│
├── services/                      # Business logic (no HTTP concerns)
│   ├── hf_chat.py                 # HuggingFace Qwen chat completions
│   ├── llava_vision.py            # LLaVA image/PDF vision extraction
│   ├── mcp_client.py              # MCP client bridge → Docker sandbox
│   ├── orchestrator.py            # LangGraph state machine (teacher → execute → debug)
│   ├── pdf_parser.py              # PyMuPDF in-memory PDF text extraction
│   └── tts.py                     # Google TTS audio generation
│
├── sandbox/                       # Docker-based code execution sandbox
│   ├── Dockerfile                 # Python 3.12 + GCC/G++ + MCP SDK
│   └── server.py                  # MCP server: execute_code tool (Python/C/C++)
│
├── frontend/                      # React frontend (Vite)
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatInterface.jsx  # Main chat UI (voice, file upload, YouTube)
│   │   │   ├── CodeEditor.jsx     # Monaco editor + terminal (Python/C/C++)
│   │   │   └── MessageBubble.jsx  # Reusable message bubble component
│   │   ├── services/
│   │   │   └── api.js             # API service layer (AbortController)
│   │   ├── App.jsx                # Root component (dashboard layout)
│   │   ├── App.css                # Global styles & design system
│   │   └── main.jsx               # Vite entry point
│   ├── package.json
│   └── vite.config.js
│
└── README.md                      # ← You are here
```

---

## 🏗️ Architecture Overview

### Upload Pipeline (Phases 3–5)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User Uploads File                           │
└────────────────────────────┬────────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         ┌─────────┐  ┌───────────┐  ┌───────────┐
         │  PDF     │  │  PDF      │  │  Image    │
         │ Digital  │  │ Scanned   │  │ Direct    │
         │ PyMuPDF  │  │ LLaVA     │  │ LLaVA     │
         └────┬─────┘  └─────┬─────┘  └─────┬─────┘
              └──────────────┼──────────────┘
                             ▼
              ┌──────────────────────────────┐
              │  LangGraph Orchestrator      │
              │                              │
              │  Teacher → Code Extractor    │
              │      ↓                       │
              │  Execution (Docker sandbox)  │
              │      ↓                       │
              │  Debugger (max 3 retries)    │
              └──────────────┬───────────────┘
                             ▼
              ┌──────────────────────────────┐
              │  Final Lesson + Code Output  │
              │  + TTS Audio                 │
              └──────────────────────────────┘
```

### Code Execution Sandbox (Phase 5)

```
┌──────────────────────────────────────────────────────────────┐
│  React CodeEditor (Monaco)                                   │
│  Language: Python 🐍 │ C ⚙️ │ C++ ⚡                         │
│  "Run Code" → POST /execute-code { code, language }         │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI /execute-code                                       │
│  → MCP Client (services/mcp_client.py)                      │
│  → Spins up fresh Docker container per execution             │
│  → --network none │ --memory 256m │ --cpus 0.5               │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  Docker Container (explainai-sandbox)                        │
│                                                              │
│  Python:  python3 script.py     (stdin=DEVNULL, 3s timeout) │
│  C:       gcc code.c -o code_exec && ./code_exec            │
│  C++:     g++ code.cpp -o code_exec && ./code_exec          │
│                                                              │
│  Returns: { stdout, error, compile_error }                  │
└──────────────────────────────────────────────────────────────┘
```

---

## 🚀 Setup Instructions

### Prerequisites

| Tool        | Version | Required For              |
| ----------- | ------- | ------------------------- |
| Python      | 3.10+   | Backend                   |
| Node.js     | 18+     | Frontend                  |
| npm         | 8+      | Frontend                  |
| Ollama      | Latest  | Vision (LLaVA)            |
| Docker      | 24+     | Code execution sandbox    |

### 1. Ollama (Local Vision AI)

```bash
# Install Ollama — https://ollama.com/download
# Then pull the LLaVA vision model (~4.7 GB, one-time download):
ollama pull llava
```

### 2. Docker Sandbox (Code Execution)

```bash
# Install Docker Desktop — https://docs.docker.com/desktop/install/
# Then build the sandbox image:
docker build -t explainai-sandbox ./sandbox

# Verify:
docker run --rm --entrypoint python3 explainai-sandbox -c "from server import LANGUAGE_CONFIG; print(list(LANGUAGE_CONFIG.keys()))"
# Expected: ['python', 'c', 'cpp']
```

### 3. Backend (FastAPI)

```bash
# Create & activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Configure your API key
# Create a .env file in the project root with:
HUGGINGFACE_API_KEY=hf_your_key_here

# Start the backend server
uvicorn main:app --reload
```

The API will be live at **http://127.0.0.1:8000**.  
Interactive docs available at **http://127.0.0.1:8000/docs**.

### 4. Frontend (React + Vite)

```bash
# In a separate terminal
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

The frontend will be live at **http://localhost:5173** (Vite default).

---

## ✨ Features

| Phase | Feature | Description |
|-------|---------|-------------|
| 1 | **Text Chat** | Ask any question → AI-generated explanation via Qwen 2.5 |
| 2 | **Voice I/O** | Speak questions via Distil-Whisper, hear answers via Google TTS |
| 3 | **File Upload** | PDFs (PyMuPDF) and images (LLaVA) → AI lesson generation |
| 4 | **Video & YouTube** | Upload videos or paste YouTube URLs → transcript-based lessons |
| 5 | **Code Execution** | Monaco editor (Python/C/C++) → Docker sandbox with AI debugging |

### Phase 5 Highlights

- **Multi-language sandbox** — Python, C, and C++ with 3-second hard timeouts
- **Self-correcting debugger** — LangGraph loop auto-fixes runtime errors (max 3 attempts)
- **Smart error routing** — SyntaxError, compile errors, and timeouts skip the debugger (no wasted LLM calls)
- **Complete isolation** — each execution spins up a fresh container with no network, capped memory/CPU

---

## 🗺️ Roadmap

| Phase | Feature              | Status      |
| ----- | -------------------- | ----------- |
| 1     | Text-to-Text Chat    | ✅ Complete |
| 2     | Audio / Voice        | ✅ Complete |
| 3     | Multimodal Uploads   | ✅ Complete |
| 4     | Video / YouTube      | ✅ Complete |
| 5     | Code Execution       | ✅ Complete |

---

## 🔑 Environment Variables

| Variable              | Description                        | Required | Default                  |
| --------------------- | ---------------------------------- | -------- | ------------------------ |
| `HUGGINGFACE_API_KEY`  | Your Hugging Face API token        | ✅       | —                        |
| `OLLAMA_BASE_URL`      | Ollama server URL                  | ❌       | `http://localhost:11434` |

> ⚠️ **Never commit your `.env` file.** Make sure it is listed in `.gitignore`.

---

## 📄 License

This project is for personal / educational use.
