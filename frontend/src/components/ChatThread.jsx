import React, { useRef, useState } from "react";
import MessageBubble from "./MessageBubble.jsx";
import CitationPanel from "./CitationPanel.jsx";
import { streamChat, sendFeedback } from "../api.js";

let nextId = 1;

const SUGGESTIONS = [
  "How do I fix an ImagePullBackOff error?",
  "What does CrashLoopBackOff mean and how do I debug it?",
  "What's the rolling update strategy for the checkout-api Deployment?",
];

export default function ChatThread({ docTitle }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeCitation, setActiveCitation] = useState(null);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);
  const listEndRef = useRef(null);

  React.useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  function updateLastMessage(patch) {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      next[next.length - 1] = { ...last, ...patch };
      return next;
    });
  }

  async function submitQuery(query) {
    if (!query || isStreaming) return;

    setError(null);
    setInput("");

    // History sent to the backend: only role+content, in the OpenAI-style
    // shape the /chat endpoint expects.
    const history = messages
      .filter((m) => m.content)
      .map((m) => ({ role: m.role, content: m.content }));

    const userMessage = { id: nextId++, role: "user", content: query };
    const assistantMessage = {
      id: nextId++,
      role: "assistant",
      content: "",
      citations: [],
      streaming: true,
      refused: false,
      rating: null,
    };
    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(
        { query, history, docTitle },
        (event) => {
          if (event.type === "token") {
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              next[next.length - 1] = { ...last, content: last.content + event.text };
              return next;
            });
          } else if (event.type === "refused") {
            updateLastMessage({ content: event.text, refused: true, streaming: false });
          } else if (event.type === "done") {
            updateLastMessage({
              citations: event.citations,
              streaming: false,
            });
          }
        },
        { signal: controller.signal }
      );
    } catch (err) {
      setError(err.message);
      updateLastMessage({ streaming: false });
    } finally {
      setIsStreaming(false);
      updateLastMessage({ streaming: false });
    }
  }

  async function handleFeedback(messageId, rating) {
    const assistantIndex = messages.findIndex((m) => m.id === messageId);
    const message = messages[assistantIndex];
    if (!message) return;
    setMessages((prev) =>
      prev.map((m) => (m.id === messageId ? { ...m, rating } : m))
    );
    const precedingUser = [...messages.slice(0, assistantIndex)]
      .reverse()
      .find((m) => m.role === "user");
    try {
      await sendFeedback({
        query: precedingUser?.content || "",
        answer: message.content,
        rating,
        citations: message.citations || [],
      });
    } catch {
      // Feedback logging is best-effort; don't interrupt the chat over it.
    }
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
                  <button key={s} className="suggestion-chip" onClick={() => submitQuery(s)}>
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
                  onFeedback={(rating) => handleFeedback(m.id, rating)}
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
            submitQuery(input.trim());
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
