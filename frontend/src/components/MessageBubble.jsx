/**
 * MessageBubble.jsx — A single chat message rendered as a styled bubble.
 *
 * Props:
 *   role    – "user" | "assistant"  (determines alignment & colour)
 *   content – The text to display inside the bubble.
 */



import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";

export default function MessageBubble({ role, content, isGenerating, onUpdate }) {
  const isUser = role === "user";
  const [displayedText, setDisplayedText] = useState(isUser ? content : "");

  useEffect(() => {
    if (isUser) {
      setDisplayedText(content);
      return;
    }

    // Typewriter effect loop
    let timeoutId;
    const updateText = () => {
      setDisplayedText((prev) => {
        if (prev.length < content.length) {
          // Pull 1-2 characters at a time to keep up
          const charsToPull = Math.min(2, content.length - prev.length);
          const nextText = content.slice(0, prev.length + charsToPull);
          
          if (onUpdate) {
            // Trigger auto-scroll on next frame
            requestAnimationFrame(onUpdate);
          }
          
          // Randomize typing speed slightly for human-like feel (15-25ms)
          const delay = Math.floor(Math.random() * 10) + 15;
          timeoutId = setTimeout(updateText, delay);
          
          return nextText;
        }
        return prev;
      });
    };

    updateText();

    return () => clearTimeout(timeoutId);
  }, [content, isUser, onUpdate]);

  // If we are actively generating, but the displayed text has caught up to the content buffer, 
  // it means we are waiting on a tool call or network latency.
  const isStalled = isGenerating && !isUser && displayedText.length === content.length && content.length > 0;

  return (
    <div className={`message-row ${isUser ? "message-row--user" : "message-row--ai"}`}>
      {/* Small role label above the bubble */}
      <span className="message-label">{isUser ? "You" : "Teacher AI"}</span>

      <div className={`message-bubble ${isUser ? "message-bubble--user" : "message-bubble--ai"}`}>
        <div className="prose prose-invert max-w-none">
          <ReactMarkdown>
            {displayedText || ""}
          </ReactMarkdown>
        </div>
      </div>

      {isStalled && (
        <div className="mt-2 text-sm text-gray-400 italic flex items-center gap-2" style={{ animation: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite" }}>
          <span className="dot-pulse" style={{ width: "6px", height: "6px" }} />
          👨‍🏫 Teacher is firing up the code sandbox...
        </div>
      )}
    </div>
  );
}
