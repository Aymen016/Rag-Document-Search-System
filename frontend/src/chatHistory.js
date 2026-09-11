const SESSIONS_KEY = "docschat.sessions.v1";
const ACTIVE_KEY = "docschat.activeSessionId.v1";

export function loadSessions() {
  try {
    const raw = localStorage.getItem(SESSIONS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveSessions(sessions) {
  try {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
  } catch {
    // Storage can be full or blocked (private browsing); history just won't persist.
  }
}

export function loadActiveId() {
  try {
    return localStorage.getItem(ACTIVE_KEY);
  } catch {
    return null;
  }
}

export function saveActiveId(id) {
  try {
    localStorage.setItem(ACTIVE_KEY, id);
  } catch {
    // Same as above — non-fatal.
  }
}

export function newSession() {
  return {
    id: `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    title: "New chat",
    messages: [],
    streaming: false,
    updatedAt: Date.now(),
  };
}

export function newMessageId() {
  return `m_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

// A reload while a response was still streaming leaves a stale in-flight
// flag behind — nothing will ever resolve it, since the fetch that owned it
// is gone. Clear those so the UI doesn't show a permanently "generating"
// message with no way to finish.
export function sanitizeSessions(sessions) {
  return sessions.map((s) => ({
    ...s,
    streaming: false,
    messages: s.messages.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
  }));
}

export function deriveTitle(messages) {
  const firstUser = messages.find((m) => m.role === "user" && m.content);
  if (!firstUser) return "New chat";
  const text = firstUser.content.trim();
  return text.length > 42 ? `${text.slice(0, 42)}…` : text;
}

export function timeAgo(ts) {
  const diffMs = Date.now() - ts;
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return "Just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return new Date(ts).toLocaleDateString();
}
