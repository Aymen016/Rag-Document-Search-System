import React, { useState } from "react";
import ChatThread from "./components/ChatThread.jsx";
import IngestPanel from "./components/IngestPanel.jsx";

export default function App() {
  const [tab, setTab] = useState("chat");

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
        <nav className="tabs">
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
            Chat
          </button>
          <button className={tab === "ingest" ? "active" : ""} onClick={() => setTab("ingest")}>
            Ingest
          </button>
        </nav>
      </header>
      <main>{tab === "chat" ? <ChatThread docTitle={null} /> : <IngestPanel />}</main>
    </div>
  );
}
