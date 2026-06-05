<div align="center">
  <h1>🚀 Multimodal AI Explainer Platform</h1>
  <p><strong>Enterprise-grade AI tutoring and interactive learning platform built with LangGraph, Qwen2.5-VL, and E2B Code Interpreter.</strong></p>
  <br />
</div>

## 📖 Overview

The **Multimodal AI Explainer Platform** is a cutting-edge educational assistant that bridges the gap between passive consumption and active learning. It acts as an interactive AI tutor capable of processing YouTube videos, local documents (PDFs), and direct audio/visual input to synthesize, explain, and evaluate technical concepts in real time. 

By leveraging **LangGraph** for multi-agent orchestration and an **E2B Docker Sandbox** for secure code execution, users can chat, write code, and seamlessly debug logic alongside an autonomous AI.

---

## ✨ Features

- 🧠 **LangGraph Multi-Agent Orchestration:** Complex workflows are managed dynamically by stateful, multi-step agent interactions, ensuring the AI correctly scopes, plans, and executes tutoring workflows.
- 🛠️ **E2B Autonomous Debugging Sandbox:** Safely execute Python, C, and C++ code directly in the browser via an isolated E2B cloud container. The AI can autonomously intercept stack traces and automatically suggest fixes using the "Magic Wand" debugger.
- 👁️ **Zero-Latency Local Multimodal Vision:** Powered by **Qwen-VL** and **PyMuPDF**, the platform analyzes complex visual content and documents (hybrid PDFs, handwritten diagrams) in real time with minimal latency.
- 🎓 **Pydantic-Enforced AI Quiz Generation:** Features a distraction-free "Focus Mode" that generates dynamic, context-aware interactive quizzes using Hugging Face Inference endpoints and strict Pydantic JSON schemas.
- 🎙️ **Audio Processing:** Effortless extraction and processing of local video and audio using **MoviePy** and **Whisper**.

---

## 🛠️ Tech Stack

### Frontend
- **React.js** with Vite for lightning-fast HMR
- **react-resizable-panels** for a professional IDE-like layout
- **Monaco Editor** & **XTerm.js** for an authentic coding and terminal experience
- **Vanilla CSS** with glassmorphism, dynamic animations, and rich aesthetics

### Backend
- **FastAPI** & **Uvicorn** for high-performance Python asynchronous routing
- **Pydantic** for rigid data validation and AI output enforcement
- **WebSockets** for real-time sandbox terminal streaming

### AI & Infrastructure
- **LangGraph** for deterministic agent graphs
- **E2B Code Interpreter** for secure, isolated code execution
- **Local Ollama** (Qwen2.5 / Qwen2.5-VL) for private, offline intelligence
- **Hugging Face API** for fast serverless generation
- **MoviePy & PyMuPDF** for media ingestion and document extraction

---

## 🚀 How to Run Locally

### Prerequisites
- [Node.js](https://nodejs.org/en/) (v18+)
- [Python](https://www.python.org/) (3.10+)
- [Ollama](https://ollama.ai/) installed locally and running `qwen2.5` / `qwen2.5-vl`
- E2B API Key (for the code execution sandbox)
- Hugging Face API Key (for quiz generation)

### 1. Backend Setup

Open a terminal and navigate to the project root:

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your environment variables
cp .env.example .env
# Edit .env and add your E2B_API_KEY and HF_API_KEY

# 4. Start the FastAPI server
uvicorn main:app --reload
```
*The backend will be running on `http://localhost:8000`.*

### 2. Frontend Setup

Open a new terminal window and navigate to the `frontend` folder:

```bash
# 1. Navigate to the frontend directory
cd frontend

# 2. Install Node dependencies
npm install

# 3. Start the Vite dev server
npm run dev
```
*The React app will be running on `http://localhost:5173` (or the port specified by Vite).*

---

## 📁 Repository Structure Blueprint
*(See documentation for full architecture breakdown)*

- `backend/` - FastAPI routes, LangGraph services, and core orchestration
- `frontend/` - React application, UI components, and API integration
- `sandbox/` - E2B Docker configurations and execution logic

---
<div align="center">
  <i>Built with ❤️ for modern engineering teams and educators.</i>
</div>
