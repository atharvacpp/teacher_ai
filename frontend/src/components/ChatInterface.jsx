/**
 * ChatInterface.jsx — Main chat UI layout for ExplainAI.
 *
 * Manages:
 *  • input     – current text in the input field
 *  • messages  – array of { role: "user"|"assistant", content: string }
 *  • loading   – whether we are waiting for an AI response
 *
 * Delegates the actual API call to services/api.js.
 */

import React, { useState, useRef, useEffect } from "react";
import MessageBubble from "./MessageBubble";
import { sendChatMessage } from "../services/api";

export default function ChatInterface() {
  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------
  const [input, setInput] = useState("");           // Controlled text input
  const [messages, setMessages] = useState([]);     // Chat history
  const [loading, setLoading] = useState(false);    // "Thinking…" indicator

  // Ref to the bottom of the messages list so we can auto-scroll
  const messagesEndRef = useRef(null);

  // Auto-scroll to the newest message whenever the list changes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // -----------------------------------------------------------------------
  // Handlers
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
      const explanation = await sendChatMessage(updatedMessages);

      // 4. Append the assistant response (must use "assistant" role for HF API)
      const assistantMessage = { role: "assistant", content: explanation };
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
            Powered by Qwen 2.5 &mdash; Phase 1
          </p>
        </div>
      </header>

      {/* ---- Message Area ---- */}
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p className="chat-empty__icon">💬</p>
            <p className="chat-empty__text">
              Ask me anything — I'll explain it for you.
            </p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <MessageBubble key={idx} role={msg.role} content={msg.content} />
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
        <input
          id="chat-input"
          className="chat-input"
          type="text"
          placeholder="Type your question here..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
          autoFocus
        />
        <button
          id="chat-submit"
          className="chat-submit"
          type="submit"
          disabled={loading || !input.trim()}
        >
          {loading ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
