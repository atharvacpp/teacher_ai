<p align="center">
  <h1 align="center">✨ Teacher AI — Multimodal AI Coding Tutor</h1>
  <p align="center">
    An AI-powered coding tutor with voice input, code execution sandbox, video analysis, lesson generation, and an interactive quiz engine.
  </p>
</p>

---

## 🎯 Overview

Teacher AI is a full-stack AI SaaS platform that acts as your personal coding teacher. It combines multiple AI pipelines to provide an interactive learning experience:

- **Voice & Text Chat** with an AI teacher (Qwen 2.5 7B)
- **Code Execution Sandbox** with a live terminal (Docker-isolated)
- **YouTube Video Analysis** — paste a URL, get transcript-aware tutoring
- **Lesson Generation** powered by a LangGraph state machine with Self-RAG
- **AI Quiz Engine** — auto-generated quizzes from video transcripts
- **Handwriting / Image Recognition** via LLaVA vision model
- **GPU-accelerated Speech-to-Text** via Faster Whisper

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend (Vite)                │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────┐    │
│  │ Teacher  │  │    Code      │  │   Generate     │    │
│  │   AI     │  │  Assistant   │  │    Lesson      │    │
│  │  (Chat)  │  │  (Editor)    │  │  (Pipeline C)  │    │
│  └──────────┘  └──────────────┘  └────────────────┘    │
│         Collapsible Sidebar Navigation                  │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / WebSocket
┌────────────────────────┴────────────────────────────────┐
│              FastAPI Backend (uvicorn)                   │
│                                                         │
│  Routers:                                               │
│    /api/chat          → Pipeline A (Reasoning)          │
│    /api/execute       → Pipeline B (Code Execution)     │
│    /api/generate      → Pipeline C (Lesson Generation)  │
│    /ws/execute        → WebSocket live terminal         │
│    /api/quiz          → AI Quiz Engine                  │
│    /api/voice         → Speech-to-Text (Faster Whisper) │
│    /api/video         → YouTube transcript extraction   │
│                                                         │
│  Services:                                              │
│    HF Inference (Qwen) · Ollama (DeepSeek, LLaVA)      │
│    LangGraph · Groq (Llama 3) · Pinecone · DuckDuckGo  │
│    Faster Whisper (CUDA) · gTTS · MCP Sandbox Client    │
└────────────────────────┬────────────────────────────────┘
                         │
           ┌─────────────┴──────────────┐
           │   Docker Sandbox (MCP)     │
           │   Python / C / C++         │
           │   Network-isolated         │
           └────────────────────────────┘
```

---

## 🔀 AI Pipelines

### Pipeline A — Reasoning (Teacher AI Chat)
The main chat pipeline. User messages are sent to **Qwen 2.5 7B** (via HuggingFace Inference API) for conversational tutoring. Supports:
- Text chat with streaming responses
- File uploads (PDF parsing via PyMuPDF)
- Image/handwriting recognition (LLaVA via Ollama)
- Voice input (Faster Whisper ASR on GPU)
- YouTube transcript injection for video-aware tutoring

### Pipeline B — Code Execution (Code Assistant)
An interactive code editor with a live terminal powered by **Docker + WebSocket**:
- Monaco editor with Python, C, and C++ support
- Real-time stdin/stdout streaming over WebSocket
- AI debugging via **DeepSeek Coder v2** (local Ollama)
- Sandboxed execution (no network, memory/CPU/PID limits)

### Pipeline C — Lesson Generation (Generate Lesson)
A **LangGraph state machine** with a Semantic Router:

```
START → Semantic Router (Llama 3.1 8B)
            │
    ┌───────┴────────┐
    ▼                ▼
 "factual"      "educational"
    │                │
    ▼                ▼
 Factual          Self-RAG
 Search           Sub-Graph
 Node           (Pinecone +
    │            Grading +
    │            Hallucination
    │            Check)
    │                │
    ▼                ▼
  Tools ◄──► Teacher Agent (Llama 3.3 70B) ◄──► Tools
    │                │
   END              END
```

- **Semantic Router**: Classifies user intent as `factual` or `educational` using Llama 3.1 8B
- **Factual Fast-Lane**: Directly answers fact-based questions using web search
- **Educational RAG Lane**: Retrieves context from Pinecone vector DB, grades documents, checks for hallucinations, then passes grounded content to the Teacher Agent
- **Teacher Agent**: Enhances lessons with code examples (sandbox execution) and web search
- **TTS**: Generates audio narration of lessons via gTTS

---

## 🚀 Getting Started

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| **Python** | 3.11+ | Backend server |
| **Node.js** | 18+ | Frontend build |
| **Docker Desktop** | Latest | Code execution sandbox |
| **Ollama** | Latest | Local LLM hosting |
| **NVIDIA GPU** | CUDA 12.1 | Speech-to-Text acceleration |

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/teacher-ai.git
cd teacher-ai
```

### 2. Set Up Environment Variables

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

You will need:
- `HUGGINGFACE_API_KEY` — [Get one here](https://huggingface.co/settings/tokens)
- `GROQ_API_KEY` — [Get one here](https://console.groq.com/keys)
- `PINECONE_API_KEY` *(optional)* — [Get one here](https://app.pinecone.io/)

### 3. Install Python Dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Install PyTorch with CUDA Support

> ⚠️ **Do NOT install torch from PyPI.** Use the official CUDA index:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Verify GPU access:
```bash
python -c "import torch; print(torch.cuda.is_available())"
# Should print: True
```

### 5. Pull Ollama Models

```bash
ollama pull deepseek-coder-v2
ollama pull llava
```

### 6. Build the Docker Sandbox
and open the docker desktop app 
```bash
cd sandbox
docker build -t explainai-sandbox .
cd ..
```

### 7. Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

### 8. Start the Application

You need **3 terminals** running simultaneously:

**Terminal 1 — Ollama Server** *(if not already running as a service)*
```bash
ollama serve
```

**Terminal 2 — Backend (FastAPI)**
```bash
uvicorn main:app --reload
```
Backend runs at: `http://localhost:8000`

**Terminal 3 — Frontend (Vite)**
```bash
cd frontend
npm run dev
```
Frontend runs at: `http://localhost:5173`

> 💡 Make sure **Docker Desktop** is running before using the Code Assistant sandbox.

---

## 📁 Project Structure

```
teacher-ai/
├── main.py                          # FastAPI app entry point
├── config.py                        # Centralized configuration
├── schemas.py                       # Pydantic request/response models
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment variable template
│
├── routers/                         # API route handlers
│   ├── chat.py                      # POST /api/chat (Pipeline A)
│   ├── pipeline_a_reasoning.py      # Pipeline A reasoning logic
│   ├── pipeline_b_execution.py      # POST /api/execute (Pipeline B)
│   ├── pipeline_c.py                # POST /api/generate (Pipeline C)
│   ├── ws_execute.py                # WS /ws/execute (live terminal)
│   ├── quiz.py                      # POST /api/quiz
│   ├── video.py                     # POST /api/video/*
│   └── voice.py                     # POST /api/voice/transcribe
│
├── services/                        # Business logic & AI services
│   ├── asr.py                       # Faster Whisper (GPU ASR)
│   ├── hf_chat.py                   # HuggingFace Inference (Qwen)
│   ├── llava_vision.py              # LLaVA vision model (Ollama)
│   ├── ollama_vision.py             # Ollama vision integration
│   ├── mcp_client.py                # MCP Docker sandbox client
│   ├── pdf_parser.py                # PDF text extraction (PyMuPDF)
│   ├── pipeline_a_reasoning.py      # Pipeline A chain logic
│   ├── pipeline_b_execution.py      # Pipeline B execution logic
│   ├── pipeline_c_orchestrator.py   # Pipeline C LangGraph orchestrator
│   ├── self_rag.py                  # Self-RAG sub-graph
│   ├── rag_ingestion.py             # Pinecone document ingestion
│   └── tts.py                       # Text-to-Speech (gTTS)
│
├── sandbox/                         # Docker sandbox for code execution
│   ├── Dockerfile                   # Sandbox container image
│   └── server.py                    # MCP server inside the container
│
└── frontend/                        # React + Vite frontend
    ├── src/
    │   ├── App.jsx                  # Root layout (sidebar + workspace)
    │   ├── App.css                  # Global styles & design system
    │   ├── components/
    │   │   ├── Sidebar.jsx          # Collapsible navigation sidebar
    │   │   ├── ChatInterface.jsx    # Teacher AI chat workspace
    │   │   ├── CodeEditor.jsx       # Code Assistant workspace
    │   │   ├── LessonChat.jsx       # Generate Lesson workspace
    │   │   ├── QuizModal.jsx        # Interactive quiz overlay
    │   │   └── MessageBubble.jsx    # Chat message renderer
    │   └── services/
    │       └── api.js               # API client utilities
    ├── package.json
    └── vite.config.js
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18, Vite, Monaco Editor, xterm.js |
| **Backend** | FastAPI, Uvicorn, Python 3.11+ |
| **AI Models** | Qwen 2.5 7B (HF), Llama 3.3 70B (Groq), DeepSeek Coder v2 (Ollama), LLaVA (Ollama) |
| **Orchestration** | LangGraph, LangChain, Self-RAG |
| **Vector DB** | Pinecone |
| **ASR** | Faster Whisper (CUDA GPU) |
| **TTS** | gTTS |
| **Sandbox** | Docker + MCP Protocol |
| **Search** | DuckDuckGo |

---

## 📄 License

This project is for educational purposes.
