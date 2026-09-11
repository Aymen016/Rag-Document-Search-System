import React, { useEffect, useRef, useState } from "react";
import MessageBubble from "./MessageBubble.jsx";
import CitationPanel from "./CitationPanel.jsx";

const SUGGESTIONS = [
  "How do I fix an ImagePullBackOff error?",
  "What does CrashLoopBackOff mean and how do I debug it?",
  "What's the rolling update strategy for the checkout-api Deployment?",
];

export default function ChatThread({ messages, isStreaming, error, onSubmit, onFeedback }) {
  const [input, setInput] = useState("");
  const [activeCitation, setActiveCitation] = useState(null);
  const listEndRef = useRef(null);

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  function handleSend(query) {
    const trimmed = query.trim();
    if (!trimmed || isStreaming) return;
    onSubmit(trimmed);
    setInput("");
  }

  return (
    <div className="chat-layout">
      <div className="chat-main">
        <div className="message-list">
          {messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">
                <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <h2>Ask about your documents</h2>
              <p>
                Answers are grounded only in what's been indexed — you'll get a
                clear "I don't have enough information" instead of a guess.
              </p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} className="suggestion-chip" onClick={() => handleSend(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="message-list-inner">
              {messages.map((m) => (
                <MessageBubble
                  key={m.id}
                  message={m}
                  onCitationClick={setActiveCitation}
                  onFeedback={(rating) => onFeedback(m.id, rating)}
                />
              ))}
              {error && <p className="error-banner">{error}</p>}
              <div ref={listEndRef} />
            </div>
          )}
        </div>

        <form
          className="chat-input-row"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend(input);
          }}
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your documents..."
            disabled={isStreaming}
          />
          <button className="send-btn" type="submit" disabled={isStreaming || !input.trim()} aria-label="Send">
            <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 2 11 13" />
              <path d="M22 2 15 22l-4-9-9-4z" />
            </svg>
          </button>
        </form>
      </div>

      <CitationPanel citation={activeCitation} onClose={() => setActiveCitation(null)} />
    </div>
  );
}
