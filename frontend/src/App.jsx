/**
 * App.jsx — Root component for the ExplainAI React frontend.
 *
 * Layout: AI Tutor | Workbench (two horizontal panels).
 * YouTube videos render inline in the chat feed, not as a separate panel.
 */

import { useEffect, useState } from "react";
import {
  Group as PanelGroup,
  Panel,
  Separator as PanelResizeHandle,
  usePanelRef,
} from "react-resizable-panels";
import ChatInterface from "./components/ChatInterface";
import CodeEditor from "./components/CodeEditor";
import QuizModal from "./components/QuizModal";
import "./App.css";

function usePanelCollapsed(panelRef, collapsed) {
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    if (collapsed) {
      if (!panel.isCollapsed()) panel.collapse();
    } else if (panel.isCollapsed()) {
      panel.expand();
    }
  }, [panelRef, collapsed]);
}

export default function App() {
  const [showAgent, setShowAgent] = useState(false);
  const [showEditor, setShowEditor] = useState(false);
  const [activeVideo, setActiveVideo] = useState(null); // { id, title, transcript }
  const [showQuiz, setShowQuiz] = useState(false);

  const tutorPanelRef = usePanelRef();
  const workbenchPanelRef = usePanelRef();

  const tutorCollapsed = !showAgent;
  const workbenchCollapsed = !showEditor;

  usePanelCollapsed(tutorPanelRef, tutorCollapsed);
  usePanelCollapsed(workbenchPanelRef, workbenchCollapsed);

  const noneOpen = !showAgent && !showEditor;
  const showHandle = showAgent && showEditor;

  return (
    <div className="app">
      <div className="toggle-bar">
        <button
          id="toggle-agent"
          className={`toggle-btn ${showAgent ? "toggle-btn--active" : ""}`}
          onClick={() => setShowAgent((prev) => !prev)}
        >
          <span className="toggle-btn__icon">✨</span>
          <span className="toggle-btn__label">
            {showAgent ? "Close AI Teacher" : "Open AI Teacher"}
          </span>
        </button>

        <button
          id="toggle-editor"
          className={`toggle-btn toggle-btn--editor ${showEditor ? "toggle-btn--active" : ""}`}
          onClick={() => setShowEditor((prev) => !prev)}
        >
          <span className="toggle-btn__icon">⚡</span>
          <span className="toggle-btn__label">
            {showEditor ? "Close Code Editor" : "Open Code Editor"}
          </span>
        </button>
      </div>

      <div className="workspace-shell workspace-shell--focus">
        {noneOpen && (
          <div className="landing-page landing-page--overlay">
            <div className="landing-icon">🚀</div>
            <h2 className="landing-title">Welcome to ExplainAI</h2>
            <p className="landing-subtitle">
              Your AI-powered learning assistant. Choose a tool above to get started.
            </p>
            <div className="landing-cards">
              <div className="landing-card" onClick={() => setShowAgent(true)}>
                <span className="landing-card__icon">✨</span>
                <h3>AI Teacher</h3>
                <p>Ask questions, upload documents, analyze YouTube videos</p>
              </div>
              <div className="landing-card" onClick={() => setShowEditor(true)}>
                <span className="landing-card__icon">⚡</span>
                <h3>Code Editor</h3>
                <p>Write, run, and debug Python, C, and C++ code</p>
              </div>
            </div>
          </div>
        )}

        <PanelGroup
          id="workspace-root"
          className="workspace-panels workspace-panels--focus"
          orientation="horizontal"
        >
          <Panel
            id="tutor-panel"
            className="panel-shell panel-card tutor-panel"
            panelRef={tutorPanelRef}
            collapsible
            collapsedSize={0}
            defaultSize={58}
            minSize={28}
          >
            <ChatInterface
              activeVideo={activeVideo}
              onVideoDetect={setActiveVideo}
              onTakeQuiz={() => setShowQuiz(true)}
            />
          </Panel>

          {showHandle && (
            <PanelResizeHandle className="PanelResizeHandle PanelResizeHandle--col" />
          )}

          <Panel
            id="workbench"
            className="panel-shell panel-card workbench-panel"
            panelRef={workbenchPanelRef}
            collapsible
            collapsedSize={0}
            defaultSize={42}
            minSize={22}
          >
            <CodeEditor
              activeVideo={activeVideo}
              onTakeQuiz={() => setShowQuiz(true)}
            />
          </Panel>
        </PanelGroup>
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
