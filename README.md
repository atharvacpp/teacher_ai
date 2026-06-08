# 🎓 Teacher AI: The Multimodal AI Explainer Platform

> **Your personal, highly-energetic, open-source AI tutor.** 

Teacher AI is a state-of-the-art multimodal learning platform designed to break down complex topics into incredibly fun, engaging, and easy-to-understand explanations. By combining local autonomous agents with cloud-based vision and speech models, it allows you to learn from nearly any format—text, audio, video, or handwritten notes—and even write and debug code in an isolated sandbox!

---

## 🚀 Key Features

*   **📺 YouTube Video Extraction:** Paste any YouTube URL to instantly extract transcripts and generate engaging, comprehensive summaries of the video's core concepts.
*   **🎤 Audio Processing (Whisper):** Upload MP4s or other audio/video formats to extract speech, transcribed flawlessly via `openai/whisper-large-v3-turbo`.
*   **👁️ Multimodal Vision Processing:** Upload PDFs or images (including handwritten notes!). Processed locally via Ollama (`llava`) and PyMuPDF to extract and explain visual information.
*   **🗣️ Text-to-Speech (TTS):** Explanations are automatically converted into lifelike audio playback, so you can listen while you learn.
*   **📝 Context-Aware Quizzes:** The AI generates dynamic, JSON-structured quizzes based on the extracted transcripts or documents to test your knowledge in a distraction-free Focus Mode.
*   **💻 Local Code Execution Sandbox:** A secure Docker-powered environment to write, run, and test Python, C, and C++ code directly within the chat interface.
*   **🤖 DeepSeek Autonomous Debugger:** Click the "Magic Wand" in the code editor to trigger a local `deepseek-coder-v2` agent that autonomously finds bugs and fixes your code on the fly!

---

## 🧠 Architecture Overview

Teacher AI is powered by a robust backend built with **FastAPI** and **LangGraph**, communicating with a sleek **React (Vite)** frontend. 

The core of the logic revolves around a **LangGraph Multi-Agent state machine**:
1.  **Summarizer Node:** Ingests raw text, transcripts, or vision-extracted OCR data and compresses it into core concepts.
2.  **Teacher Node:** Takes the concepts and expands them into highly engaging, analogy-driven explanations.
3.  **Reviewer Node:** Acts as a quality-control check to ensure the explanation is accurate, properly formatted, and easy to understand.

For the coding environment, we utilize a local **FastMCP Server** connected to a Docker container. When the user hits the "Debug with AI" button, the **DeepSeek Autonomous Debugger** analyzes the code and terminal output to intelligently rewrite the active file.

---

## 🛠️ Prerequisites

Before you begin, ensure you have the following installed:

*   **Node.js** (v18+ recommended) for the React frontend.
*   **Python 3.10+** for the FastAPI backend.
*   **Docker** for running the isolated code execution sandbox.
*   **[Ollama](https://ollama.com/)** for running local vision and debugging models.

---

## ⚡ Step-by-Step Quickstart Guide

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/teacher-ai.git
cd teacher-ai
```

### 2. Set Up the Backend
Install the Python dependencies:
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy the template environment file:
```bash
cp .env.example .env
```
Open `.env` and add your **HuggingFace API Key** (required for the cloud-based Qwen chat and Whisper ASR models).

### 4. Pull Local Models via Ollama
Ensure Docker or Ollama is running, then pull the required models:
```bash
ollama run llava               # For Vision / PDF OCR
ollama run deepseek-coder-v2   # For Autonomous Code Debugging
```

### 5. Build the Code Execution Sandbox
Build the Docker image used for running user code safely:
```bash
# run docker engine before this 
cd sandbox
docker build -t aethernet-sandbox .
cd ..
```

### 6. Start the Services
Start the **FastAPI Backend** (from the root directory):
```bash
uvicorn main:app --reload
```

In a new terminal window, start the **React Frontend**:
```bash
cd frontend
npm install
npm run dev
```

Open your browser to `http://localhost:5173` and start learning! 🎓
