import React from "react";

const CITATION_RE = /\[(\d+)\]/g;

/**
 * Splits message text on [1], [2]... markers and renders the valid ones as
 * clickable buttons that open the citation in the side panel. Citation IDs
 * that don't match anything in `citations` (hallucinated ones the backend
 * already flagged) render as plain text instead of a broken link.
 */
function renderWithCitations(text, citations, onCitationClick) {
  const byId = Object.fromEntries(citations.map((c) => [c.id, c]));
  const parts = [];
  let lastIndex = 0;
  let match;
  let key = 0;

  CITATION_RE.lastIndex = 0;
  while ((match = CITATION_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={key++}>{text.slice(lastIndex, match.index)}</span>);
    }
    const id = Number(match[1]);
    const citation = byId[id];
    if (citation) {
      parts.push(
        <button
          key={key++}
          className="citation-marker"
          onClick={() => onCitationClick(citation)}
          title={citation.doc_title}
        >
          [{id}]
        </button>
      );
    } else {
      parts.push(<span key={key++}>[{id}]</span>);
    }
    lastIndex = match.index + match[0].length;
  }
  parts.push(<span key={key++}>{text.slice(lastIndex)}</span>);
  return parts;
}

function Avatar({ role }) {
  if (role === "user") {
    return (
      <div className="avatar user">
        <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      </div>
    );
  }
  return (
    <div className="avatar assistant">
      <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1a7 7 0 0 1-7 7h-4a7 7 0 0 1-7-7H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z" />
        <circle cx="9" cy="14" r="1" fill="currentColor" />
        <circle cx="15" cy="14" r="1" fill="currentColor" />
      </svg>
    </div>
  );
}

export default function MessageBubble({ message, onCitationClick, onFeedback }) {
  const isUser = message.role === "user";
  const isThinking = message.streaming && !message.content;
  const [copied, setCopied] = React.useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be denied by the browser; fail silently.
    }
  }

  return (
    <div className={`message-row ${isUser ? "user" : "assistant"}`}>
      <Avatar role={message.role} />
      <div className="message-col">
        <div className="message-bubble">
          {isUser ? (
            message.content
          ) : isThinking ? (
            <span className="typing-dots">
              <span />
              <span />
              <span />
            </span>
          ) : (
            <div className="message-text">
              {renderWithCitations(message.content, message.citations || [], onCitationClick)}
              {message.streaming && <span className="cursor">▍</span>}
            </div>
          )}
          {message.refused && (
            <div className="refused-badge">No confident answer in the documents</div>
          )}
        </div>
        {!isUser && !message.streaming && message.content && (
          <div className="feedback-row">
            <button
              className={`feedback-btn ${message.rating === "up" ? "active" : ""}`}
              onClick={() => onFeedback("up")}
              aria-label="Good answer"
            >
              <svg viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M7 22V11l5-8a2.5 2.5 0 0 1 2.5 2.5V10h5.7a2 2 0 0 1 1.98 2.3l-1.38 8A2 2 0 0 1 18.85 22H7Z" />
                <path d="M7 11H4a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h3" />
              </svg>
            </button>
            <button
              className={`feedback-btn ${message.rating === "down" ? "active" : ""}`}
              onClick={() => onFeedback("down")}
              aria-label="Bad answer"
            >
              <svg viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 2v11l-5 8a2.5 2.5 0 0 1-2.5-2.5V14H3.8a2 2 0 0 1-1.98-2.3l1.38-8A2 2 0 0 1 5.15 2H17Z" />
                <path d="M17 13h3a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1h-3" />
              </svg>
            </button>
            <button
              className={`feedback-btn ${copied ? "copied" : ""}`}
              onClick={handleCopy}
              aria-label="Copy answer"
              title="Copy answer"
            >
              {copied ? (
                <svg viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
