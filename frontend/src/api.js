const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/**
 * POST /chat streams Server-Sent Events. Native EventSource only supports
 * GET requests with no body, so we parse the SSE framing by hand over a
 * fetch() ReadableStream instead.
 *
 * Calls onEvent({type, ...}) for each event as it arrives:
 *   {type: "chunks", chunks: [...]}
 *   {type: "token", text: "..."}
 *   {type: "done", text, citations, hallucinated_ids}
 *   {type: "refused", reason, text}
 */
export async function streamChat({ query, history = [], docTitle = null }, onEvent, { signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, history, doc_title: docTitle }),
    signal,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Chat request failed (${response.status}): ${detail}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line; each frame has "data: <json>"
    // lines (and sometimes an "event:" line, which we only use for "end").
    const frames = buffer.split("\n\n");
    buffer = frames.pop(); // last element may be an incomplete frame

    for (const frame of frames) {
      const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      const json = dataLine.slice("data:".length).trim();
      if (!json) continue;
      const event = JSON.parse(json);
      onEvent(event);
    }
  }
}

export async function uploadFiles(files, subfolder = "uploaded") {
  const formData = new FormData();
  for (const file of files) formData.append("files", file);
  const response = await fetch(
    `${API_BASE_URL}/ingest/upload?subfolder=${encodeURIComponent(subfolder)}`,
    { method: "POST", body: formData }
  );
  if (!response.ok) throw new Error(`Upload failed (${response.status})`);
  return response.json();
}

export async function runIngest() {
  const response = await fetch(`${API_BASE_URL}/ingest/run`, { method: "POST" });
  if (!response.ok) throw new Error(`Ingest run failed (${response.status})`);
  return response.json();
}

export async function listSources() {
  const response = await fetch(`${API_BASE_URL}/sources`);
  if (!response.ok) throw new Error(`Failed to list sources (${response.status})`);
  return response.json();
}

export async function sendFeedback({ query, answer, rating, citations = [] }) {
  const response = await fetch(`${API_BASE_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, answer, rating, citations }),
  });
  if (!response.ok) throw new Error(`Feedback failed (${response.status})`);
  return response.json();
}
