/**
 * ChatInterface.jsx — Main chat UI layout for ExplainAI.
 *
 * Manages:
 *  • input          – current text in the input field
 *  • messages       – array of { role: "user"|"assistant", content: string }
 *  • loading        – whether we are waiting for an AI response
 *  • isRecording    – whether the microphone is actively capturing audio
 *  • transcribing   – whether an audio clip is being transcribed server-side
 *  • youtubeUrl     – YouTube URL entered by the user (Phase 4)
 *  • showYouTubeInput – whether the YouTube URL bar is visible
 *
 * Delegates the actual API calls to services/api.js.
 */

import { useState, useRef, useEffect } from "react";
import MessageBubble from "./MessageBubble";
import { useChatStream } from "../hooks/useChatStream";
import {
  transcribeAudio,
  uploadFile,
  processYouTubeVideo,
} from "../services/api";

// ---------------------------------------------------------------------------
// YouTube Video ID Extraction
// ---------------------------------------------------------------------------

/**
 * Extract a YouTube video ID from various URL formats:
 *   - https://www.youtube.com/watch?v=VIDEO_ID
 *   - https://youtu.be/VIDEO_ID
 *   - https://youtube.com/embed/VIDEO_ID
 *   - https://www.youtube.com/shorts/VIDEO_ID
 * Returns null if no valid ID is found.
 */
function extractYouTubeId(url) {
  if (!url) return null;
  const str = url.trim();
  
  // If it's exactly 11 characters (raw ID)
  if (/^[a-zA-Z0-9_-]{11}$/.test(str)) {
    return str;
  }

  const patterns = [
    /(?:youtube\.com\/watch\?.*v=)([a-zA-Z0-9_-]{11})/,
    /(?:youtu\.be\/)([a-zA-Z0-9_-]{11})/,
    /(?:youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})/,
    /(?:youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})/,
    /(?:m\.youtube\.com\/watch\?.*v=)([a-zA-Z0-9_-]{11})/,
    /v=([a-zA-Z0-9_-]{11})/, // fallback for any URL containing v=
  ];
  
  for (const pattern of patterns) {
    const match = str.match(pattern);
    if (match) return match[1];
  }
  return null;
}

export default function ChatInterface({ activeVideo, onVideoDetect, onTakeQuiz }) {
  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------
  const [input, setInput] = useState("");           // Controlled text input
  const [messages, setMessages] = useState(() => {
    const saved = sessionStorage.getItem('aethernet_chat_history');
    console.log('Loading from sessionStorage (chat_history):', saved);
    if (!saved) return [];
    try {
      const parsed = JSON.parse(saved);
      // If the user refreshes while audio is generating, the request dies.
      // We must clear the pending state so it doesn't spin forever.
      return parsed.map(msg => ({ ...msg, audioPending: false }));
    } catch (e) {
      return [];
    }
  });     // Chat history
  const [loading, setLoading] = useState(false);    // "Thinking…" indicator
  const [statusText, setStatusText] = useState(""); // Granular loading status
  const [isRecording, setIsRecording] = useState(false);   // Mic active?
  const [transcribing, setTranscribing] = useState(false); // ASR in-flight?
  const [selectedFile, setSelectedFile] = useState(null);  // File attachment
  const [forceVision, setForceVision] = useState(false);   // Handwriting mode
  
  const [showYouTubeInput, setShowYouTubeInput] = useState(false); // YT bar visible?
  const [youtubeUrl, setYoutubeUrl] = useState("");                // YT URL value

  const { streamAssistantReply, stopGeneration } = useChatStream({
    setMessages,
    setLoading,
    setStatusText,
  });

  // -----------------------------------------------------------------------
  // Session Persistence: Save on Update
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (messages && messages.length > 0) {
      sessionStorage.setItem('aethernet_chat_history', JSON.stringify(messages));
    }
  }, [messages]);

  // Refs
  const messagesEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const fileInputRef = useRef(null);

  // Auto-scroll to the newest message whenever the list changes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);



  // -----------------------------------------------------------------------
  // Stop Generation Handler
  // -----------------------------------------------------------------------

  /** Called when the user clicks the "Stop ⏹" button. */
  function handleStop() {
    stopGeneration();
  }

  // -----------------------------------------------------------------------
  // Chat Handler
  // -----------------------------------------------------------------------

  async function submitPrompt(promptText) {
    if (loading) return;
    
    const userMessage = { role: "user", content: promptText };
    const updatedMessages = [...messages, userMessage];
    
    setMessages(updatedMessages);
    setInput("");
    setLoading(true);
    setStatusText("");
    
    try {
      await streamAssistantReply(updatedMessages);
    } catch (error) {
      if (
        error.message !== "Generation stopped by user." &&
        !error.message.includes("Error in input stream") &&
        error.name !== "AbortError"
      ) {
        setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ Something went wrong: ${error.message}` }]);
      }
    }
  }

  /** Called when the user clicks "Send" or presses Enter. */
  async function handleSubmit(e) {
    e?.preventDefault();

    const trimmed = input.trim();
    // Allow submission if there is a file OR text
    if ((!trimmed && !selectedFile) || loading) return; 

    // Detect YouTube URLs in normal chat messages
    const videoId = extractYouTubeId(trimmed);
    if (videoId) {
      // If it's a YouTube URL, intercept it and process it using the YouTube pipeline
      if (onVideoDetect) {
        onVideoDetect({ id: videoId, title: "YouTube Video", transcript: null });
      }
      
      const userMessage = { role: "user", content: `📺 YouTube: ${trimmed}`, videoId };
      const updatedMessages = [...messages, userMessage];
      setMessages(updatedMessages);
      setInput("");
      setLoading(true);

      try {
        const response = await processYouTubeVideo(trimmed);
        const assistantMessage = {
          role: "assistant",
          content: response.explanation,
          audio_base64: response.audio_base64,
        };
        setMessages((prev) => [...prev, assistantMessage]);
        
        if (onVideoDetect) {
          onVideoDetect({ id: videoId, title: "YouTube Video", transcript: response.transcript });
        }
      } catch (error) {
        if (
          error.message !== "Generation stopped by user." &&
          !error.message.includes("Error in input stream") &&
          error.name !== "AbortError"
        ) {
          setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ Something went wrong: ${error.message}` }]);
        }
      } finally {
        setLoading(false);
        setStatusText("");
      }
      return;
    }

    // 1. Build the user message visual
    let userContent = trimmed;
    if (selectedFile) {
      userContent = `📎 Attached: ${selectedFile.name}${trimmed ? `\n\n${trimmed}` : ""}`;
    }

    const userMessage = { role: "user", content: userContent };
    const updatedMessages = [...messages, userMessage];

    // 2. Immediately show the user's message in the chat
    setMessages(updatedMessages);
    setInput("");       // Clear the input field
    const fileToUpload = selectedFile;
    setSelectedFile(null); // Clear the attachment chip
    setLoading(true);   // Show the "Thinking…" indicator
    setStatusText("");  // Clear previous status

    try {
      // 3. Branch logic based on whether a file is attached
      if (fileToUpload) {
        const assistantMsgId = `msg-${Date.now()}-${Math.random()}`;
        setMessages((prev) => [...prev, { id: assistantMsgId, role: "assistant", content: "", audio_base64: null, audioPending: true }]);
        let finalTranscript = null;

        await uploadFile(
          fileToUpload,
          trimmed,
          forceVision,
          (chunk) => {
            setMessages((prev) => prev.map(m => 
              m.id === assistantMsgId ? { ...m, content: m.content + chunk } : m
            ));
          },
          (audio) => {
            setMessages((prev) => prev.map(m => 
              m.id === assistantMsgId ? { ...m, audio_base64: audio, audioPending: false } : m
            ));
          },
          (transcript) => {
            finalTranscript = transcript;
          },
          () => {
            // onDone: stream fully closed (after TTS)
            setLoading(false); // Fallback
            setStatusText("");
            setMessages((prev) => prev.map(m => 
              m.id === assistantMsgId ? { ...m, audioPending: false } : m
            ));
          },
          (status) => {
            setStatusText(status);
          },
          () => {
            // onTextComplete: text finished — unlock UI, enable quiz
            setLoading(false);
            setStatusText("");
            if (fileToUpload.type?.startsWith("video/") && finalTranscript && onVideoDetect) {
              onVideoDetect({ 
                id: `local-${Date.now()}`, 
                title: fileToUpload.name, 
                transcript: finalTranscript 
              });
            }
          }
        );
      } else {
        await streamAssistantReply(updatedMessages);
      }
    } catch (error) {
      // Distinguish user-initiated stops from real errors
      if (
        !error.message.includes("Error in input stream") &&
        error.message !== "Generation stopped by user." &&
        error.name !== "AbortError"
      ) {
        const errorMessage = {
          role: "assistant",
          content: `⚠️ Something went wrong: ${error.message}`,
        };
        setMessages((prev) => [...prev, errorMessage]);
      }
    }
  }

  // -----------------------------------------------------------------------
  // Voice Recording Handlers
  // -----------------------------------------------------------------------

  /** Start capturing audio from the user's microphone. */
  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Explicitly pick a known mimeType so we know exactly what the backend
      // receives.  Fallback order: webm → mp4 → browser default.
      let mimeType = "";
      if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
        mimeType = "audio/webm;codecs=opus";
      } else if (MediaRecorder.isTypeSupported("audio/webm")) {
        mimeType = "audio/webm";
      } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
        mimeType = "audio/mp4";
      }
      // If none matched, let the browser choose (mimeType stays "")

      const recorderOptions = mimeType ? { mimeType } : undefined;
      const mediaRecorder = new MediaRecorder(stream, recorderOptions);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        // Stop all tracks to release the mic immediately
        stream.getTracks().forEach((track) => track.stop());

        const blobType = mimeType || "audio/webm";
        const audioBlob = new Blob(audioChunksRef.current, { type: blobType });

        // Don't send empty recordings
        if (audioBlob.size === 0) {
          return;
        }

        setTranscribing(true);

        try {
          const text = await transcribeAudio(audioBlob);

          if (text && text.trim()) {
            // Completely overwrite the current value of the text input
            setInput(text);
          } else {
            alert("Transcription returned empty — please try speaking louder or try again.");
          }
        } catch (err) {
          console.error("[ChatInterface] Transcription failed:", err);
          // Alert the user with the specific error message
          alert(`Transcription failed: ${err.message}`);
        } finally {
          // ALWAYS reset the transcribing state so the UI stops spinning
          setTranscribing(false);
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("[ChatInterface] Microphone access denied:", err);
      alert(
        "Microphone access was denied. Please allow microphone permissions and try again."
      );
    }
  }

  /** Stop the current recording — this triggers onstop → transcription. */
  function stopRecording() {
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state !== "inactive"
    ) {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  }

  /** Toggle recording on / off. */
  function handleMicClick() {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  }

  // -----------------------------------------------------------------------
  // File Upload Handlers
  // -----------------------------------------------------------------------

  function handleFileChange(e) {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0]);
    }
    // Clear the input value so the same file can be selected again if needed
    e.target.value = null;
  }

  function clearFile() {
    setSelectedFile(null);
    setForceVision(false);
  }

  // -----------------------------------------------------------------------
  // YouTube Handler
  // -----------------------------------------------------------------------

  /** Submit a YouTube URL for transcript-based explanation. */
  async function handleYouTubeSubmit(e) {
    e.preventDefault();

    const url = youtubeUrl.trim();
    if (!url || loading) return;

    // Extract video ID for iframe embedding
    const videoId = extractYouTubeId(url);
    if (videoId && onVideoDetect) {
      onVideoDetect({ id: videoId, title: "YouTube Video", transcript: null }); // placeholder until fetched
    }

    // Show the user's URL in the chat
    const userMessage = { role: "user", content: `📺 YouTube: ${url}`, videoId };
    setMessages((prev) => [...prev, userMessage]);
    setYoutubeUrl("");
    setShowYouTubeInput(false);
    setLoading(true);

    try {
      const assistantMsgId = `msg-${Date.now()}-${Math.random()}`;
      setMessages((prev) => [...prev, { id: assistantMsgId, role: "assistant", content: "", audio_base64: null, audioPending: true }]);
      let finalTranscript = null;

      await processYouTubeVideo(
        url,
        (chunk) => {
          setMessages((prev) => prev.map(m => 
            m.id === assistantMsgId ? { ...m, content: m.content + chunk } : m
          ));
        },
        (audio) => {
          setMessages((prev) => prev.map(m => 
            m.id === assistantMsgId ? { ...m, audio_base64: audio, audioPending: false } : m
          ));
        },
        (transcript) => {
          finalTranscript = transcript;
        },
        () => {
          // onDone: stream fully closed (after TTS)
          setLoading(false); // Fallback
          setMessages((prev) => prev.map(m => 
            m.id === assistantMsgId ? { ...m, audioPending: false } : m
          ));
        },
        (status) => {
          setStatusText(status);
        },
        () => {
          // onTextComplete: text finished — unlock UI, enable quiz immediately
          setLoading(false);
          setStatusText("");
          if (videoId && onVideoDetect && finalTranscript) {
            onVideoDetect({ id: videoId, title: "YouTube Video", transcript: finalTranscript });
          }
        }
      );
    } catch (error) {
      if (
        error.message !== "Generation stopped by user." &&
        !error.message.includes("Error in input stream") &&
        error.name !== "AbortError"
      ) {
        setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ Something went wrong: ${error.message}` }]);
      }
    } finally {
      setLoading(false);
    }
  }

  const lastMessage = messages[messages.length - 1];
  const isStreaming = lastMessage?.role === "assistant" && lastMessage?.content !== "";

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------
  return (
    <div className="chat-container">
      {/* ---- Header ---- */}
      <header className="chat-header">
        <div className="chat-header-info">
          <div className="chat-header__icon">✨</div>
          <div className="chat-header__titles">
            <h1 className="chat-header__title">Teacher AI</h1>
            <p className="chat-header__subtitle">
              Your personal AI coding teacher
            </p>
          </div>
        </div>
        <div className="chat-header-actions" style={{ display: 'flex', gap: '8px' }}>
          <button 
            className="new-chat-btn" 
            onClick={onTakeQuiz}
            disabled={!activeVideo?.transcript}
            title={activeVideo?.transcript ? "Take a quiz based on the loaded video transcript" : "Load a YouTube video first to take a quiz"}
            style={{ 
              background: 'transparent', 
              border: '1px solid var(--color-border)', 
              opacity: !activeVideo?.transcript ? 0.5 : 1,
              cursor: !activeVideo?.transcript ? 'not-allowed' : 'pointer'
            }}
          >
            🎯 Take Quiz
          </button>
          <button className="new-chat-btn" onClick={() => setMessages([])}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{marginRight: "6px", verticalAlign: "-2px"}}>
               <path d="M12 5v14M5 12h14"/>
            </svg>
            New Chat
          </button>
        </div>
      </header>

      {/* ---- Message Area ---- */}
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="empty-greeting">
              <span className="empty-greeting-icon">👋</span>
              <div className="empty-greeting-text">
                <h2>Hello! I'm your AI coding teacher.</h2>
                <p>I can help you learn, debug, and build amazing projects.<br/>What would you like to learn or ask today?</p>
              </div>
            </div>

            <div className="empty-suggestions-wrapper">
              <p className="empty-suggestions-title">Try asking about</p>
              <div className="empty-suggestions-grid">
                <button className="suggestion-card" onClick={() => submitPrompt("Explain Python basics like variables and data types.")}>
                  <div className="suggestion-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
                  </div>
                  <div className="suggestion-text">
                    <h4>Python Basics</h4>
                    <p>Variables, data types, I/O</p>
                  </div>
                  <div className="suggestion-arrow">›</div>
                </button>
                <button className="suggestion-card" onClick={() => submitPrompt("Explain Python Data Structures like lists, tuples, dictionaries.")}>
                  <div className="suggestion-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
                  </div>
                  <div className="suggestion-text">
                    <h4>Data Structures</h4>
                    <p>Lists, tuples, dictionaries</p>
                  </div>
                  <div className="suggestion-arrow">›</div>
                </button>
                <button className="suggestion-card" onClick={() => submitPrompt("Explain Python Control Flow: if-else, loops, conditions.")}>
                  <div className="suggestion-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 16 16 12 12 8"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
                  </div>
                  <div className="suggestion-text">
                    <h4>Control Flow</h4>
                    <p>If-else, loops, conditions</p>
                  </div>
                  <div className="suggestion-arrow">›</div>
                </button>
                <button className="suggestion-card" onClick={() => submitPrompt("Explain File Handling in Python: reading and writing files.")}>
                  <div className="suggestion-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                  </div>
                  <div className="suggestion-text">
                    <h4>File Handling</h4>
                    <p>Reading and writing files</p>
                  </div>
                  <div className="suggestion-arrow">›</div>
                </button>
                <button className="suggestion-card" onClick={() => submitPrompt("Explain Python Functions: defining, calling, returning.")}>
                  <div className="suggestion-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="12" y1="8" x2="12" y2="16"/></svg>
                  </div>
                  <div className="suggestion-text">
                    <h4>Functions</h4>
                    <p>Defining, calling, returning</p>
                  </div>
                  <div className="suggestion-arrow">›</div>
                </button>
                <button className="suggestion-card" onClick={() => submitPrompt("Explain Object Oriented Programming in Python: classes, objects, inheritance.")}>
                  <div className="suggestion-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
                  </div>
                  <div className="suggestion-text">
                    <h4>OOP in Python</h4>
                    <p>Classes, objects, inheritance</p>
                  </div>
                  <div className="suggestion-arrow">›</div>
                </button>
              </div>
            </div>

            <div className="empty-divider">
              <span>or ask anything...</span>
            </div>
          </div>
        )}

        {messages.map((msg, idx) => {
          const isYouTube = Boolean(msg.videoId);
          const isThisActiveVideo = activeVideo?.id === msg.videoId;
          const transcriptLoaded = isThisActiveVideo && Boolean(activeVideo?.transcript);

          return (
            <div key={msg.id ?? idx} className="message-container">
              <MessageBubble 
                role={msg.role} 
                content={msg.content} 
              />
              
              {/* Inline YouTube Player */}
              {isYouTube && (
                <div className="inline-video-card" style={{ marginTop: "12px", background: "rgba(255,255,255,0.02)", border: "1px solid rgba(139, 92, 246, 0.15)", borderRadius: "12px", overflow: "hidden" }}>
                  <div className="youtube-embed__wrapper" style={{ height: "260px", position: "relative" }}>
                    <iframe
                      src={`https://www.youtube.com/embed/${msg.videoId}`}
                      title="YouTube video player"
                      style={{ border: "none", width: "100%", height: "100%", position: "absolute", inset: 0 }}
                      allow="fullscreen"
                      allowFullScreen
                    />
                  </div>
                </div>
              )}

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

        {/* Thinking indicator / Stop Button */}
        {loading && (
          <div className="message-row message-row--ai" style={{ width: isStreaming ? "100%" : "auto", maxWidth: "100%" }}>
            {!isStreaming && (
              <>
                <span className="message-label">Teacher AI</span>
                <div className="message-bubble message-bubble--ai thinking-bubble">
                  <span className="dot-pulse" />
                  {statusText ? statusText : selectedFile?.type?.startsWith("video/") ? "Analyzing video..." : "Thinking…"}
                  <button
                    id="stop-generation"
                    className="stop-button"
                    type="button"
                    onClick={handleStop}
                    title="Stop generation"
                    aria-label="Stop generation"
                  >
                    Stop ⏹
                  </button>
                </div>
              </>
            )}
            {isStreaming && (
              <div style={{ display: "flex", justifyContent: "center", marginTop: "8px", width: "100%" }}>
                <button
                  id="stop-generation"
                  className="stop-button"
                  type="button"
                  onClick={handleStop}
                  title="Stop generation"
                  aria-label="Stop generation"
                >
                  Stop ⏹
                </button>
              </div>
            )}
          </div>
        )}

        {/* Invisible anchor for auto-scroll */}
        <div ref={messagesEndRef} />
      </div>

      {/* ---- Input Area ---- */}
      <div className="chat-input-wrapper">
        {selectedFile && (
          <div className="attachment-bar">
            <div className="attachment-chip">
              <span className="attachment-chip__text">
                {selectedFile.type?.startsWith("video/") ? "🎥 " : "📎 "}
                {selectedFile.name}
              </span>
              <button
                type="button"
                className="attachment-chip__remove"
                onClick={clearFile}
                title="Remove attachment"
              >
                ×
              </button>
            </div>

            {/* Show handwriting toggle only for PDFs */}
            {selectedFile?.type === "application/pdf" && (
              <label
                id="handwriting-toggle"
                className={`vision-toggle ${forceVision ? "vision-toggle--active" : ""}`}
                title="Enable this for PDFs containing handwriting, diagrams, or scanned content. Uses the slower LLaVA vision pipeline."
              >
                <span className="vision-toggle__track">
                  <input
                    type="checkbox"
                    className="vision-toggle__input"
                    checked={forceVision}
                    onChange={(e) => setForceVision(e.target.checked)}
                  />
                  <span className="vision-toggle__slider" />
                </span>
                <span className="vision-toggle__label">
                  <svg className="vision-toggle__icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                  Analyze Handwriting or Complex Structures
                  <span className="vision-toggle__badge">Slower</span>
                </span>
              </label>
            )}
          </div>
        )}

        {/* ---- YouTube URL Input Bar ---- */}
        {showYouTubeInput && (
          <form className="youtube-input-bar" onSubmit={handleYouTubeSubmit}>
            <div className="youtube-input-bar__icon">📺</div>
            <input
              id="youtube-url-input"
              className="youtube-input-bar__input"
              type="url"
              placeholder="Paste a YouTube URL…"
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              disabled={loading}
              autoFocus
            />
            <button
              id="youtube-submit"
              type="submit"
              className="youtube-input-bar__submit"
              disabled={loading || !youtubeUrl.trim()}
            >
              Explain
            </button>
            <button
              type="button"
              className="youtube-input-bar__close"
              onClick={() => { setShowYouTubeInput(false); setYoutubeUrl(""); }}
              title="Close"
              aria-label="Close YouTube input"
            >
              ×
            </button>
          </form>
        )}

        <form className="chat-input-area" onSubmit={handleSubmit}>
          {/* Hidden File Input */}
          <input
            type="file"
            ref={fileInputRef}
            style={{ display: "none" }}
            accept="image/*,application/pdf,video/*"
            onChange={handleFileChange}
          />

          <div className="chat-input-box">
            <textarea
              id="chat-input"
              className="chat-input"
              placeholder={
                transcribing
                  ? "Transcribing your voice…"
                  : isRecording
                  ? "🎙️ Listening…"
                  : "Type your question here..."
              }
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              disabled={loading || isRecording}
              autoFocus
              rows={1}
            />

            <div className="chat-input-footer">
              <div className="chat-input-actions">
                <button
                  type="button"
                  className="action-icon-btn"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={loading || transcribing}
                  title="Attach file"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                  </svg>
                </button>

                <button
                  id="mic-button"
                  className={`action-icon-btn ${isRecording ? "action-icon-btn--recording" : ""}`}
                  type="button"
                  onClick={handleMicClick}
                  disabled={loading || transcribing}
                  title={isRecording ? "Stop recording" : "Start voice input"}
                >
                  {isRecording ? (
                    <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor">
                      <rect x="4" y="4" width="10" height="10" rx="2" />
                    </svg>
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="9" y="1" width="6" height="12" rx="3" />
                      <path d="M5 10a7 7 0 0 0 14 0" />
                      <line x1="12" y1="17" x2="12" y2="21" />
                      <line x1="8" y1="21" x2="16" y2="21" />
                    </svg>
                  )}
                </button>

                <button
                  id="youtube-toggle"
                  type="button"
                  className={`action-icon-btn ${showYouTubeInput ? "action-icon-btn--active" : ""}`}
                  onClick={() => setShowYouTubeInput((prev) => !prev)}
                  disabled={loading || transcribing}
                  title="Explain a YouTube video"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
                  </svg>
                </button>
              </div>

              <button
                id="chat-submit"
                className="chat-submit-btn"
                type="submit"
                disabled={loading || (!input.trim() && !selectedFile) || isRecording || transcribing}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{marginRight: 6}}>
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
                {loading ? "..." : "Send"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
