# 🧠 ExplainAI — Multimodal AI Web Application

> **Phase 1** · Text-to-Text inference powered by [Qwen/Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) via the Hugging Face Inference API.

---

## 📁 Project Structure

```
explain_ai/
│
├── main.py                        # FastAPI backend (API server)
├── requirements.txt               # Python dependencies
├── .env                           # Environment variables (API keys — git-ignored)
│
├── frontend/                      # React frontend (Vite)
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatInterface.jsx  # Main chat UI layout & state management
│   │   │   └── MessageBubble.jsx  # Reusable message bubble component
│   │   ├── services/
│   │   │   └── api.js             # API service layer (fetch to backend)
│   │   ├── App.jsx                # Root component
│   │   ├── App.css                # Global styles & design system
│   │   └── main.jsx               # Vite entry point
│   ├── package.json
│   └── vite.config.js
│
└── README.md                      # ← You are here
```

---

## 🚀 Setup Instructions

### Prerequisites

| Tool    | Version |
| ------- | ------- |
| Python  | 3.10+   |
| Node.js | 18+     |
| npm     | 8+      |

### 1. Backend (FastAPI)

```bash
# Create & activate a virtual environment
python3 -m venv .venv
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

### 2. Frontend (React + Vite)

```bash
# In a separate terminal
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

The frontend will be live at **http://localhost:3000** (or `:3001` if 3000 is in use).

---

## ✨ Current Features (Phase 1)

- **Text-to-Text Chat** — Ask any question and receive an AI-generated explanation.
- **Model** — [Qwen/Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) via the Hugging Face Inference API.
- **Modern Dark UI** — Glassmorphism card layout, gradient message bubbles, smooth animations.
- **Real-time Feedback** — Thinking indicator while the AI generates a response.
- **Error Handling** — Graceful inline error messages if the backend is unreachable.

---

## 🗺️ Roadmap

| Phase | Feature              | Status      |
| ----- | -------------------- | ----------- |
| 1     | Text-to-Text Chat    | ✅ Complete |
| 2     | Image Understanding  | 🔜 Planned  |
| 3     | Audio / TTS          | 🔜 Planned  |
| 4     | Video Analysis       | 🔜 Planned  |

---

## 🔑 Environment Variables

| Variable              | Description                        | Required |
| --------------------- | ---------------------------------- | -------- |
| `HUGGINGFACE_API_KEY`  | Your Hugging Face API token        | ✅       |

> ⚠️ **Never commit your `.env` file.** Make sure it is listed in `.gitignore`.

---

## 📄 License

This project is for personal / educational use.
