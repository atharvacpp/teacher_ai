import { useState, useRef, useEffect } from "react";
import MessageBubble from "./MessageBubble";
import { generateLesson, ingestMemory } from "../services/api";
import "../App.css";

export default function LessonChat({ onClose = null }) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState(() => {
    const saved = sessionStorage.getItem('lesson_chat_history');
    if (!saved) return [];
    try {
      return JSON.parse(saved);
    } catch (e) {
      return [];
    }
  });
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [sandboxArtifacts, setSandboxArtifacts] = useState(() => {
    const saved = sessionStorage.getItem('lesson_sandbox_artifacts');
    if (!saved) return [];
    try {
      return JSON.parse(saved);
    } catch (e) {
      return [];
    }
  });
  const [showSandbox, setShowSandbox] = useState(false);
  const [activeFileId, setActiveFileId] = useState(null);

  const [isUploadingMemory, setIsUploadingMemory] = useState(false);
  const fileInputRef = useRef(null);

  const messagesEndRef = useRef(null);

  // Persist messages to sessionStorage
  useEffect(() => {
    if (messages.length > 0) {
      sessionStorage.setItem('lesson_chat_history', JSON.stringify(messages));
    }
  }, [messages]);

  // Persist sandbox artifacts to sessionStorage
  useEffect(() => {
    if (sandboxArtifacts.length > 0) {
      sessionStorage.setItem('lesson_sandbox_artifacts', JSON.stringify(sandboxArtifacts));
    }
  }, [sandboxArtifacts]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleMemoryUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    setIsUploadingMemory(true);
    
    // Optional: add a temporary message to the chat
    const tempMsgId = `memory-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: tempMsgId, role: "user", content: `Uploading ${file.name} to AI Memory...` }
    ]);

    try {
      const result = await ingestMemory(file);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `✅ **Memory Updated:** Successfully memorized ${file.name} (${result.chunks_created} chunks stored).` }
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `❌ **Upload Failed:** ${err.message}` }
      ]);
    } finally {
      setIsUploadingMemory(false);
      // reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  async function handleSubmit(e) {
    e?.preventDefault();
    const topic = input.trim();
    if (!topic || loading) return;

    const userMessage = { role: "user", content: topic };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);
    setStatusText("Preparing...");

    try {
      const assistantMsgId = `msg-${Date.now()}`;
      setMessages((prev) => [
        ...prev,
        { id: assistantMsgId, role: "assistant", content: "", audioPending: true }
      ]);

      await generateLesson(
        topic,
        (chunk) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, content: m.content + chunk } : m
            )
          );
        },
        (audio) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, audio_base64: audio, audioPending: false } : m
            )
          );
        },
        null,
        () => {
          setLoading(false);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, audioPending: false } : m
            )
          );
        },
        (status) => {
          setStatusText(status);
        },
        () => {
          setLoading(false);
          setStatusText("");
        },
        (artifact) => {
          setSandboxArtifacts((prev) => [...prev, artifact]);
          setShowSandbox(true);
        }
      );
    } catch (error) {
      if (error.name !== "AbortError") {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `⚠️ Error: ${error.message}` }
        ]);
      }
    } finally {
      setLoading(false);
    }
  }

  const hasArtifacts = sandboxArtifacts.length > 0;

  const chatUI = (
    <div className="chat-container" style={{ width: "100%", height: "100%", borderRight: hasArtifacts ? "1px solid var(--border-color)" : "none", borderRadius: "16px", display: "flex", flexDirection: "column" }}>
      {/* ---- Header ---- */}
      <header className="chat-header">
        <div className="chat-header-info">
          <div className="chat-header__icon">🎓</div>
          <div className="chat-header__titles">
            <h1 className="chat-header__title">Lesson Generator</h1>
            <p className="chat-header__subtitle">
              Enter a topic to generate a comprehensive AI-powered lesson.
            </p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleMemoryUpload} 
            style={{ display: "none" }} 
            accept=".pdf,.txt,.md"
          />
          <button 
            className="new-chat-btn" 
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploadingMemory}
            style={{ background: 'var(--color-primary)', color: '#fff', border: 'none' }}
          >
            <span style={{ marginRight: "6px", fontSize: "1rem", verticalAlign: "-1px" }}>🧠</span>
            {isUploadingMemory ? "Memorizing..." : "Upload to Memory"}
          </button>
          <button className="new-chat-btn" onClick={() => { setMessages([]); setSandboxArtifacts([]); sessionStorage.removeItem('lesson_chat_history'); sessionStorage.removeItem('lesson_sandbox_artifacts'); }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "6px", verticalAlign: "-2px" }}>
              <path d="M12 5v14M5 12h14" />
            </svg>
            New Topic
          </button>
          {onClose && (
            <button className="new-chat-btn" onClick={onClose} style={{ background: 'var(--color-surface-hover)' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: "6px", verticalAlign: "-2px" }}>
                <line x1="19" y1="12" x2="5" y2="12"></line>
                <polyline points="12 19 5 12 12 5"></polyline>
              </svg>
              Back to Workspace
            </button>
          )}
        </div>
      </header>

      {/* ---- Message Area ---- */}
      <div className="chat-messages flex-1 overflow-y-auto min-h-0 p-4 pb-24" style={{ flexGrow: 1 }}>
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="empty-greeting">
              <span className="empty-greeting-icon">🎓</span>
              <div className="empty-greeting-text">
                <h2>Ready to learn?</h2>
                <p>I can generate structured, detailed lessons on any topic.<br />What would you like to explore today?</p>
              </div>
            </div>
          </div>
        )}

        {messages.map((msg, idx) => {
          const isLast = idx === messages.length - 1;
          return (
            <div key={msg.id ?? idx} className="message-container">
              <MessageBubble 
                role={msg.role} 
                content={msg.content} 
                isGenerating={loading && isLast}
                onUpdate={() => {
                  messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
                }}
              />
              {msg.role === "assistant" && msg.audioPending && !msg.audio_base64 && (
                <p className="audio-pending-indicator" aria-live="polite">
                  Preparing audio…
                </p>
              )}
            {msg.role === "assistant" && msg.audio_base64 && (
              <audio
                controls
                src={`data:audio/mpeg;base64,${msg.audio_base64}`}
                className="message-audio-player mt-3 w-full"
              />
            )}
          </div>
          );
        })}
        {loading && (
          <div className="message-row message-row--ai" style={{ width: "auto" }}>
            <span className="message-label">Teacher AI</span>
            <div className="message-bubble message-bubble--ai thinking-bubble">
              <span className="dot-pulse" />
              {statusText || "Thinking…"}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ---- Input Area ---- */}
      <div className="chat-input-wrapper" style={{ padding: "16px 20px" }}>
        <form className="chat-input-area" onSubmit={handleSubmit}>
          <div className="chat-input-box" style={{ paddingRight: '8px' }}>
            <textarea
              id="chat-input"
              className="chat-input"
              placeholder="Type a topic (e.g. React Hooks, Neural Networks)..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              disabled={loading}
              autoFocus
              rows={1}
            />

            <div className="chat-input-footer" style={{ borderTop: 'none', paddingTop: '0', display: 'flex', justifyContent: 'flex-end', marginTop: '-8px' }}>
              <button
                className="chat-submit-btn"
                type="submit"
                disabled={loading || !input.trim()}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 6 }}>
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
                {loading ? "..." : "Generate"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );

  if (!hasArtifacts || !showSandbox) {
    return (
      <div style={{ position: "relative", height: "100%" }}>
        {chatUI}
        {hasArtifacts && !showSandbox && (
          <button 
            onClick={() => setShowSandbox(true)}
            style={{ position: "absolute", top: "16px", right: "16px", padding: "8px 16px", background: "var(--color-primary)", color: "white", borderRadius: "8px", border: "none", cursor: "pointer", fontWeight: "bold" }}
          >
            Show Sandbox Executions ({sandboxArtifacts.length})
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="locked-workspace-grid" style={{ height: "100%" }}>
      <div className="locked-panel-left flex flex-col h-full overflow-hidden">
        {chatUI}
      </div>
      <div className="locked-panel-right flex flex-col h-full" style={{ background: "var(--color-surface)", borderRadius: "16px", position: "relative", overflow: "auto" }}>
        <div style={{ padding: "16px", borderBottom: "1px solid var(--border-color)", display: "flex", justifyContent: "space-between", alignItems: "center", background: "var(--color-bg)" }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div className="chat-header__icon" style={{ fontSize: '1.2rem', padding: '6px' }}>🛠️</div>
            <h2 style={{ margin: 0, fontSize: '1.2rem' }}>Sandbox Executions</h2>
          </div>
          <button 
            onClick={() => setShowSandbox(false)}
            style={{ background: "transparent", color: "var(--text-secondary)", border: "none", fontSize: "1.5rem", cursor: "pointer" }}
            title="Close Panel"
          >
            ×
          </button>
        </div>

        {sandboxArtifacts.length > 0 && (() => {
          const art = sandboxArtifacts[sandboxArtifacts.length - 1];
          return (
            <div className="flex-1 min-h-0 overflow-y-auto p-4">
              {/* Code Section */}
              <div className="rounded-t-lg p-4 bg-gray-900 text-gray-200 font-mono text-sm">
                <div className="text-xs text-gray-400 mb-2 font-bold uppercase tracking-wider">Executed Code</div>
                <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                  {art.code || "# No code provided"}
                </pre>
              </div>

              {/* Terminal Output Section */}
              <div className="rounded-b-lg bg-black text-green-400 font-mono p-4 border-t border-gray-700">
                <div className="flex justify-between items-center mb-4">
                  <span className="text-xs text-gray-500 font-bold uppercase tracking-wider">Terminal Output</span>
                  <span style={{ color: art.has_error ? "#ef4444" : "#22c55e", fontSize: "0.8rem", fontWeight: "bold" }}>
                    {art.has_error ? "Error" : "Success"}
                  </span>
                </div>
                <pre style={{ margin: 0, whiteSpace: "pre-wrap", color: art.has_error ? "#ef4444" : "inherit" }}>
                  {art.output || "(no output)"}
                </pre>

                {/* Images */}
                {art.images && art.images.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-gray-800">
                    {art.images.map((img, i) => (
                      <img key={i} src={`data:image/png;base64,${img}`} alt="Generated graph" className="max-w-full rounded bg-white p-2" style={{ marginBottom: i < art.images.length - 1 ? "12px" : 0 }} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}
