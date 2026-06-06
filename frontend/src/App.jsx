/**
 * App.jsx — Root component for the ExplainAI React frontend.
 *
 * Layout: Fixed 50/50 split dashboard.
 */

import { useEffect, useState } from "react";
import ChatInterface from "./components/ChatInterface";
import CodeEditor from "./components/CodeEditor";
import QuizModal from "./components/QuizModal";
import "./App.css";

export default function App() {
  const [activeVideo, setActiveVideo] = useState(() => {
    const saved = sessionStorage.getItem('aethernet_transcript');
    console.log('Loading from sessionStorage (transcript):', saved);
    return saved ? JSON.parse(saved) : null;
  }); // { id, title, transcript }
  
  const [showQuiz, setShowQuiz] = useState(false);

  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('aethernet_theme') || "vs-dark";
  });

  useEffect(() => {
    localStorage.setItem('aethernet_theme', theme);
  }, [theme]);

  // -----------------------------------------------------------------------
  // Session Persistence: Save on Update
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (activeVideo) {
      sessionStorage.setItem('aethernet_transcript', JSON.stringify(activeVideo));
    }
  }, [activeVideo]);

  return (
    <div className={`app ${theme === "vs-light" ? "light-theme" : ""}`}>
      <header className="aether-header">
        <div className="aether-logo">
          <div className="aether-icon-bg">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="aether-icon">
              <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              <path d="m19 8-7 7-7-7" />
            </svg>
            <span className="aether-sparkle">✨</span>
          </div>
          <div className="aether-logo-text">
            <h1>Teacher AI</h1>
            <p>Your personal AI coding teacher</p>
          </div>
        </div>
        <div className="header-actions-wrapper" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button 
            className="icon-btn" 
            title="Toggle Theme" 
            onClick={() => setTheme(prev => prev === "vs-dark" ? "vs-light" : "vs-dark")}
            style={{ marginRight: '8px' }}
          >
            {theme === "vs-dark" ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
            )}
          </button>
          <div className="header-actions-container" id="header-actions-portal">
            {/* Action buttons will be portaled here from CodeEditor */}
          </div>
        </div>
      </header>

      <div className="aether-layout">
        <main className="workspace-canvas">
          <div className="locked-workspace-grid">
            <div className="locked-panel-left">
              <ChatInterface
                activeVideo={activeVideo}
                onVideoDetect={setActiveVideo}
                onTakeQuiz={() => setShowQuiz(true)}
              />
            </div>
            
            <div className="locked-panel-right">
              <CodeEditor
                activeVideo={activeVideo}
                onTakeQuiz={() => setShowQuiz(true)}
                theme={theme}
              />
            </div>
          </div>
        </main>
      </div>

      {/* ── Focus Mode Quiz ── */}
      {showQuiz && activeVideo?.transcript && (
        <QuizModal
          videoId={activeVideo.id}
          videoTitle={activeVideo.title}
          videoTranscript={activeVideo.transcript}
          onClose={() => setShowQuiz(false)}
        />
      )}
    </div>
  );
}
