import React, { useEffect, useState } from "react";
import ChatThread from "./components/ChatThread.jsx";
import IngestPanel from "./components/IngestPanel.jsx";

function getInitialTheme() {
  const stored = localStorage.getItem("theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [tab, setTab] = useState("chat");
  const [theme, setTheme] = useState(getInitialTheme);
  const [chatKey, setChatKey] = useState(0);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <div className="logo-mark">
            <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <div className="brand-text">
            <h1>Docs Chat</h1>
            <span>Grounded Q&A over your ingested documents</span>
          </div>
        </div>
        <div className="header-actions">
          {tab === "chat" && (
            <button className="icon-btn" onClick={() => setChatKey((k) => k + 1)} aria-label="New chat" title="New chat">
              <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 5v14M5 12h14" />
              </svg>
            </button>
          )}
          <button
            className="icon-btn"
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            aria-label="Toggle theme"
            title="Toggle theme"
          >
            {theme === "dark" ? (
              <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z" />
              </svg>
            )}
          </button>
          <nav className="tabs">
            <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
              Chat
            </button>
            <button className={tab === "ingest" ? "active" : ""} onClick={() => setTab("ingest")}>
              Ingest
            </button>
          </nav>
        </div>
      </header>
      <main>{tab === "chat" ? <ChatThread key={chatKey} docTitle={null} /> : <IngestPanel />}</main>
    </div>
  );
}
