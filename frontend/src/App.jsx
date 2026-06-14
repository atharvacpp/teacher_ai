/**
 * App.jsx — Root component for the ExplainAI React frontend.
 *
 * Layout: Collapsible sidebar + full-width workspace.
 * Three tabs: Teacher AI (chat), Code Assistant (editor), Generate Lesson.
 */

import { useEffect, useState } from "react";
import Sidebar from "./components/Sidebar";
import ChatInterface from "./components/ChatInterface";
import CodeEditor from "./components/CodeEditor";
import QuizModal from "./components/QuizModal";
import LessonChat from "./components/LessonChat";
import "./App.css";

export default function App() {
  // -----------------------------------------------------------------------
  // Sidebar State
  // -----------------------------------------------------------------------
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [activeTab, setActiveTab] = useState("teacher");

  // -----------------------------------------------------------------------
  // Shared App State (preserved from original)
  // -----------------------------------------------------------------------
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

  // Session Persistence: Save on Update
  useEffect(() => {
    if (activeVideo) {
      sessionStorage.setItem('aethernet_transcript', JSON.stringify(activeVideo));
    }
  }, [activeVideo]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------
  return (
    <div className={`app ${theme === "vs-light" ? "light-theme" : ""}`}>
      {/* ── Sidebar ── */}
      <Sidebar
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen((prev) => !prev)}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        theme={theme}
        onToggleTheme={() => setTheme((prev) => prev === "vs-dark" ? "vs-light" : "vs-dark")}
      />

      {/* ── Full-Width Content Area ── */}
      <div className="workspace-full">
        {activeTab === "teacher" && (
          <ChatInterface
            activeVideo={activeVideo}
            onVideoDetect={setActiveVideo}
            onTakeQuiz={() => setShowQuiz(true)}
          />
        )}

        {activeTab === "code" && (
          <CodeEditor
            activeVideo={activeVideo}
            onTakeQuiz={() => setShowQuiz(true)}
            theme={theme}
          />
        )}

        {activeTab === "lesson" && (
          <LessonChat />
        )}
      </div>

      {/* ── Focus Mode Quiz (overlay) ── */}
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
