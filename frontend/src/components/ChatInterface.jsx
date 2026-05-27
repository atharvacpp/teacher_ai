/**
 * ChatInterface.jsx — Main chat UI layout for ExplainAI.
 *
 * Manages:
 *  • input        – current text in the input field
 *  • messages     – array of { role: "user"|"assistant", content: string }
 *  • loading      – whether we are waiting for an AI response
 *  • isRecording  – whether the microphone is actively capturing audio
 *  • transcribing – whether an audio clip is being transcribed server-side
 *
 * Delegates the actual API calls to services/api.js.
 */

import React, { useState, useRef, useEffect } from "react";
import MessageBubble from "./MessageBubble";
import { sendChatMessage, transcribeAudio } from "../services/api";

export default function ChatInterface() {
  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------
  const [input, setInput] = useState("");           // Controlled text input
  const [messages, setMessages] = useState([]);     // Chat history
  const [loading, setLoading] = useState(false);    // "Thinking…" indicator
  const [isRecording, setIsRecording] = useState(false);   // Mic active?
  const [transcribing, setTranscribing] = useState(false); // ASR in-flight?

  // Refs
  const messagesEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  // Auto-scroll to the newest message whenever the list changes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // -----------------------------------------------------------------------
  // Chat Handler
  // -----------------------------------------------------------------------

  /** Called when the user clicks "Send" or presses Enter. */
  async function handleSubmit(e) {
    e.preventDefault();

    const trimmed = input.trim();
    if (!trimmed || loading) return; // Ignore empty or duplicate submissions

    // 1. Build a temporary array with the full conversation + new user message
    const userMessage = { role: "user", content: trimmed };
    const updatedMessages = [...messages, userMessage];

    // 2. Immediately show the user's message in the chat
    setMessages(updatedMessages);
    setInput("");       // Clear the input field
    setLoading(true);   // Show the "Thinking…" indicator

    try {
      // 3. Send the ENTIRE conversation history to the backend
      const { explanation, audio_base64 } = await sendChatMessage(updatedMessages);

      // 4. Append the assistant response (must use "assistant" role for HF API)
      const assistantMessage = { role: "assistant", content: explanation, audio_base64 };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      // If the request fails, show the error inline as an assistant message
      const errorMessage = {
        role: "assistant",
        content: `⚠️ Something went wrong: ${error.message}`,
      };
      setMessages((prev) => [...prev, errorMessage]);
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
            Powered by Qwen 2.5 &mdash; Phase 2
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

        {/* Thinking indicator */}
        {loading && (
          <div className="message-row message-row--ai">
            <span className="message-label">ExplainAI</span>
            <div className="message-bubble message-bubble--ai thinking-bubble">
              <span className="dot-pulse" />
              Thinking…
            </div>
          </div>
        )}

        {/* Invisible anchor for auto-scroll */}
        <div ref={messagesEndRef} />
      </div>

      {/* ---- Input Area ---- */}
      <form className="chat-input-area" onSubmit={handleSubmit}>
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
          disabled={loading || !input.trim() || isRecording || transcribing}
        >
          {loading ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
