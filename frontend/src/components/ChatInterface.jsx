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

import React, { useState, useRef, useEffect } from "react";
import MessageBubble from "./MessageBubble";
import {
  sendChatMessage,
  transcribeAudio,
  uploadFile,
  processYouTubeVideo,
  abortActiveRequest,
} from "../services/api";

export default function ChatInterface() {
  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------
  const [input, setInput] = useState("");           // Controlled text input
  const [messages, setMessages] = useState([]);     // Chat history
  const [loading, setLoading] = useState(false);    // "Thinking…" indicator
  const [isRecording, setIsRecording] = useState(false);   // Mic active?
  const [transcribing, setTranscribing] = useState(false); // ASR in-flight?
  const [selectedFile, setSelectedFile] = useState(null);  // File attachment
  const [forceVision, setForceVision] = useState(false);   // Handwriting mode
  const [showYouTubeInput, setShowYouTubeInput] = useState(false); // YT bar visible?
  const [youtubeUrl, setYoutubeUrl] = useState("");                // YT URL value

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
    abortActiveRequest();
    setLoading(false);
  }

  // -----------------------------------------------------------------------
  // Chat Handler
  // -----------------------------------------------------------------------

  /** Called when the user clicks "Send" or presses Enter. */
  async function handleSubmit(e) {
    e.preventDefault();

    const trimmed = input.trim();
    // Allow submission if there is a file OR text
    if ((!trimmed && !selectedFile) || loading) return; 

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

    try {
      let explanation, audio_base64;
      
      // 3. Branch logic based on whether a file is attached
      if (fileToUpload) {
        // Send file + prompt directly to /upload (ignores prior chat history)
        const response = await uploadFile(fileToUpload, trimmed, forceVision);
        explanation = response.explanation;
        audio_base64 = response.audio_base64;
      } else {
        // Send the ENTIRE conversation history to the backend
        const response = await sendChatMessage(updatedMessages);
        explanation = response.explanation;
        audio_base64 = response.audio_base64;
      }

      // 4. Append the assistant response (must use "assistant" role for HF API)
      const assistantMessage = { role: "assistant", content: explanation, audio_base64 };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      // Distinguish user-initiated stops from real errors
      if (error.message === "Generation stopped by user.") {
        const stopMessage = {
          role: "assistant",
          content: "⏹ Generation stopped.",
        };
        setMessages((prev) => [...prev, stopMessage]);
      } else {
        const errorMessage = {
          role: "assistant",
          content: `⚠️ Something went wrong: ${error.message}`,
        };
        setMessages((prev) => [...prev, errorMessage]);
      }
    } finally {
      setLoading(false);
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

    // Show the user's URL in the chat
    const userMessage = { role: "user", content: `📺 YouTube: ${url}` };
    setMessages((prev) => [...prev, userMessage]);
    setYoutubeUrl("");
    setShowYouTubeInput(false);
    setLoading(true);

    try {
      const response = await processYouTubeVideo(url);
      const assistantMessage = {
        role: "assistant",
        content: response.explanation,
        audio_base64: response.audio_base64,
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      if (error.message === "Generation stopped by user.") {
        setMessages((prev) => [...prev, { role: "assistant", content: "⏹ Generation stopped." }]);
      } else {
        setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ Something went wrong: ${error.message}` }]);
      }
    } finally {
      setLoading(false);
    }
  }

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------
  return (
    <div className="chat-container">
      {/* ---- Header ---- */}
      <header className="chat-header">
        <div className="chat-header__icon">✨</div>
        <div>
          <h1 className="chat-header__title">ExplainAI</h1>
          <p className="chat-header__subtitle">
            Powered by Qwen 2.5 &mdash; Phase 4
          </p>
        </div>
      </header>

      {/* ---- Message Area ---- */}
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p className="chat-empty__icon">💬</p>
            <p className="chat-empty__text">
              Ask me anything — type or use the mic 🎙️
            </p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className="message-container">
            <MessageBubble 
              role={msg.role} 
              content={msg.content} 
            />
            {msg.role === "assistant" && msg.audio_base64 && (
              <audio controls src={`data:audio/mpeg;base64,${msg.audio_base64}`} className="mt-3 w-full" />
            )}
          </div>
        ))}

        {/* Thinking indicator with Stop button */}
        {loading && (
          <div className="message-row message-row--ai">
            <span className="message-label">ExplainAI</span>
            <div className="message-bubble message-bubble--ai thinking-bubble">
              <span className="dot-pulse" />
              {selectedFile?.type?.startsWith("video/") ? "Analyzing video..." : "Thinking…"}
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
                  Analyze Handwriting
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
          
          {/* File Attachment Button */}
          <button
            type="button"
            className="file-attach-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading || transcribing}
            title="Attach file"
            aria-label="Attach file"
          >
            {/* Paperclip Icon */}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>

          {/* YouTube Button */}
          <button
            id="youtube-toggle"
            type="button"
            className={`youtube-btn ${showYouTubeInput ? "youtube-btn--active" : ""}`}
            onClick={() => setShowYouTubeInput((prev) => !prev)}
            disabled={loading || transcribing}
            title="Explain a YouTube video"
            aria-label="YouTube video input"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
            </svg>
          </button>

          {/* Microphone button */}
          <button
          id="mic-button"
          className={`mic-button ${isRecording ? "mic-button--recording" : ""}`}
          type="button"
          onClick={handleMicClick}
          disabled={loading || transcribing}
          title={isRecording ? "Stop recording" : "Start voice input"}
          aria-label={isRecording ? "Stop recording" : "Start voice input"}
        >
          {isRecording ? (
            /* Stop icon — a filled square */
            <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor">
              <rect x="3" y="3" width="12" height="12" rx="2" />
            </svg>
          ) : (
            /* Microphone icon */
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="1" width="6" height="12" rx="3" />
              <path d="M5 10a7 7 0 0 0 14 0" />
              <line x1="12" y1="17" x2="12" y2="21" />
              <line x1="8" y1="21" x2="16" y2="21" />
            </svg>
          )}
        </button>

        <input
          id="chat-input"
          className="chat-input"
          type="text"
          placeholder={
            transcribing
              ? "Transcribing your voice…"
              : isRecording
              ? "🎙️ Listening…"
              : "Type your question here..."
          }
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading || isRecording}
          autoFocus
        />
        <button
          id="chat-submit"
          className="chat-submit"
          type="submit"
          disabled={loading || (!input.trim() && !selectedFile) || isRecording || transcribing}
        >
          {loading ? "…" : "Send"}
        </button>
      </form>
      </div>
    </div>
  );
}
