import React, { useEffect, useMemo, useState } from "react";
import ChatThread from "./components/ChatThread.jsx";
import IngestPanel from "./components/IngestPanel.jsx";
import Sidebar from "./components/Sidebar.jsx";
import { loadSessions, saveSessions, loadActiveId, saveActiveId, newSession, deriveTitle } from "./chatHistory.js";

function getInitialTheme() {
  const stored = localStorage.getItem("theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [tab, setTab] = useState("chat");
  const [theme, setTheme] = useState(getInitialTheme);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sessions, setSessions] = useState(() => {
    const existing = loadSessions();
    return existing.length > 0 ? existing : [newSession()];
  });
  const [activeId, setActiveId] = useState(() => {
    const existing = loadSessions();
    const stored = loadActiveId();
    if (stored && existing.some((s) => s.id === stored)) return stored;
    return existing.length > 0 ? existing[0].id : null;
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);

  useEffect(() => {
    if (activeId) saveActiveId(activeId);
  }, [activeId]);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId) || sessions[0],
    [sessions, activeId]
  );

  function handleNewChat() {
    const s = newSession();
    setSessions((prev) => [s, ...prev]);
    setActiveId(s.id);
    setTab("chat");
    setSidebarOpen(false);
  }

  function handleSelectSession(id) {
    setActiveId(id);
    setTab("chat");
    setSidebarOpen(false);
  }

  function handleDeleteSession(id) {
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== id);
      if (next.length === 0) {
        const s = newSession();
        setActiveId(s.id);
        return [s];
      }
      if (id === activeId) setActiveId(next[0].id);
      return next;
    });
  }

  function handleMessagesChange(id, messages) {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === id
          ? { ...s, messages, updatedAt: Date.now(), title: s.title === "New chat" ? deriveTitle(messages) : s.title }
          : s
      )
    );
  }

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
          <button
            className="icon-btn sidebar-toggle"
            onClick={() => setSidebarOpen((v) => !v)}
            aria-label="Toggle chat history"
            title="Chat history"
          >
            <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 6h18M3 12h18M3 18h18" />
            </svg>
          </button>
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
      <div className="app-body">
        <Sidebar
          sessions={sessions}
          activeId={activeSession?.id}
          onSelect={handleSelectSession}
          onNew={handleNewChat}
          onDelete={handleDeleteSession}
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />
        <main>
          {tab === "chat" ? (
            <ChatThread
              key={activeSession?.id}
              initialMessages={activeSession?.messages || []}
              onMessagesChange={(msgs) => handleMessagesChange(activeSession.id, msgs)}
            />
          ) : (
            <IngestPanel />
          )}
        </main>
      </div>
    </div>
  );
}
