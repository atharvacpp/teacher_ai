/**
 * MessageBubble.jsx — A single chat message rendered as a styled bubble.
 *
 * Props:
 *   role    – "user" | "assistant"  (determines alignment & colour)
 *   content – The text to display inside the bubble.
 */



export default function MessageBubble({ role, content }) {
  const isUser = role === "user";

  return (
    <div className={`message-row ${isUser ? "message-row--user" : "message-row--ai"}`}>
      {/* Small role label above the bubble */}
      <span className="message-label">{isUser ? "You" : "Teacher AI"}</span>

      <div className={`message-bubble ${isUser ? "message-bubble--user" : "message-bubble--ai"}`}>
        {content}
      </div>
    </div>
  );
}
