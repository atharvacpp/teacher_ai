# 🧠 ExplainAI — Multimodal AI Web Application

> **Phase 3** · Text, Voice, and Multimodal inference powered by Qwen 2.5, Ollama LLaVA, and Distil-Whisper.

---

## 📁 Project Structure

```
teacher_ai/
│
├── main.py                        # FastAPI app shell (CORS, router registration)
├── config.py                      # Env vars, model IDs, shared clients
├── schemas.py                     # Pydantic request/response models
├── requirements.txt               # Python dependencies
├── .env                           # Environment variables (API keys — git-ignored)
│
├── routers/                       # FastAPI APIRouter modules (thin HTTP layer)
│   ├── chat.py                    # POST /chat — text conversation
│   ├── upload.py                  # POST /upload — image & PDF analysis
│   └── voice.py                   # POST /transcribe — speech-to-text
│
├── services/                      # Business logic (no HTTP concerns)
│   ├── hf_chat.py                 # HuggingFace Qwen chat completions
│   ├── ollama_vision.py           # Local Ollama LLaVA image extraction
│   ├── pdf_parser.py              # PyMuPDF in-memory PDF text extraction
│   └── tts.py                     # Google TTS audio generation
│
├── frontend/                      # React frontend (Vite)
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatInterface.jsx  # Main chat UI (with Stop Generation)
│   │   │   └── MessageBubble.jsx  # Reusable message bubble component
│   │   ├── services/
│   │   │   └── api.js             # API service layer (AbortController)
│   │   ├── App.jsx                # Root component
│   │   ├── App.css                # Global styles & design system
│   │   └── main.jsx               # Vite entry point
│   ├── package.json
│   └── vite.config.js
│
└── README.md                      # ← You are here
```

---

## 🏗️ Hybrid Two-Step Handoff Architecture

ExplainAI uses a **two-step pipeline** for image analysis that combines the best of local and cloud AI:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        User Uploads Image                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1 — Vision Extraction  (Local · Free · Private)             │
│                                                                     │
│  Engine:  Ollama + LLaVA (runs on your machine)                    │
│  Prompt:  "Extract all readable text, formulas, or handwriting     │
│            from this image, and provide a literal description of   │
│            any diagrams."                                          │
│  Output:  extracted_visual_context (raw text/formulas/diagrams)    │
│                                                                     │
│  ✅ No internet required    ✅ No API costs    ✅ Data stays local  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 2 — Reasoning & Explanation  (Cloud · Powerful)             │
│                                                                     │
│  Engine:  HuggingFace Qwen 2.5-7B-Instruct (serverless API)       │
│  Input:   User's prompt + extracted_visual_context                 │
│  Output:  Final detailed explanation + TTS audio                   │
│                                                                     │
│  ✅ Advanced reasoning    ✅ Context-aware    ✅ Free tier API      │
└─────────────────────────────────────────────────────────────────────┘
```

### Why Two Steps?

| Concern | Single-Model Approach | Two-Step Handoff |
|---|---|---|
| **Cost** | Cloud VLMs are expensive or unavailable on free tiers | Step 1 is 100% free (local Ollama) |
| **Privacy** | Raw images sent to cloud APIs | Only extracted *text* leaves your machine |
| **Quality** | Small VLMs produce shallow explanations | LLaVA extracts; Qwen 2.5 *reasons* — each model does what it's best at |
| **Reliability** | Cloud VLM endpoints frequently go offline | Local extraction always works; only the text reasoning needs internet |

### How PDFs Work

PDFs skip Step 1 entirely — there's no need for vision processing. PyMuPDF extracts text directly in-memory, and the extracted text is sent straight to Qwen 2.5 for explanation. This is instant and requires no GPU.

---

## 🚀 Setup Instructions

### Prerequisites

| Tool    | Version |
| ------- | ------- |
| Python  | 3.10+   |
| Node.js | 18+     |
| npm     | 8+      |
| Ollama  | Latest  |

### 1. Ollama (Local Vision AI)

```bash
# Install Ollama — https://ollama.com/download
# Then pull the LLaVA vision model (~4.7 GB, one-time download):
ollama pull llava
```

### 2. Backend (FastAPI)

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

### 3. Frontend (React + Vite)

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

## ✨ Current Features (Phases 1–3)

- **Hybrid Image Analysis (Phase 3)** — Upload images and get premium explanations via the Two-Step Handoff (LLaVA → Qwen 2.5).
- **PDF Analysis (Phase 3)** — Upload PDFs, extracted instantly in-memory via PyMuPDF and analyzed by Qwen 2.5.
- **Stop Generation** — Halt the AI mid-generation with a single click. The backend aborts the Ollama stream to save compute.
- **Voice Dictation & TTS (Phase 2)** — Speak your questions using Whisper and hear the AI's explanation spoken back via Google TTS.
- **Text-to-Text Chat (Phase 1)** — Ask any question and receive an AI-generated explanation via Hugging Face.
- **Modern Dark UI** — Glassmorphism card layout, gradient message bubbles, and sleek file attachment chips.

---

## 🗺️ Roadmap

| Phase | Feature              | Status      |
| ----- | -------------------- | ----------- |
| 1     | Text-to-Text Chat    | ✅ Complete |
| 2     | Audio / Voice        | ✅ Complete |
| 3     | Multimodal Uploads   | ✅ Complete |
| 4     | Video Analysis       | 🔜 Planned  |

---

## 🔑 Environment Variables

| Variable              | Description                        | Required | Default                  |
| --------------------- | ---------------------------------- | -------- | ------------------------ |
| `HUGGINGFACE_API_KEY`  | Your Hugging Face API token        | ✅       | —                        |
| `OLLAMA_BASE_URL`      | Ollama server URL                  | ❌       | `http://localhost:11434` |
| `OLLAMA_VLM_MODEL`     | Ollama vision model name           | ❌       | `llava`                  |

> ⚠️ **Never commit your `.env` file.** Make sure it is listed in `.gitignore`.

---

## 📄 License

This project is for personal / educational use.
