"""
FastAPI backend (Phase 6 of the plan).

Run it:      uvicorn api.main:app --reload --port 8000
Docs:        http://localhost:8000/docs

Endpoints:
  POST /ingest/upload   - upload files into data/raw/<subfolder>/
  POST /ingest/run      - run the ingestion pipeline + (re)build the search index
  GET  /sources         - list ingested documents (for the ingestion view / doc-set filter)
  POST /chat            - ask a question, streamed as Server-Sent Events
  POST /feedback        - log thumbs up/down on an answer
  GET  /health          - liveness check
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import config
from generation.answer import generate_answer
from generation.llm_client import get_llm_client
from ingest.pipeline import run as run_pipeline
from retrieval.rerank import get_reranker
from retrieval.search import HybridRetriever, build_index

app = FastAPI(title="RAG over Messy Technical Docs")

# Any localhost port — Vite defaults to 5173 but falls back to 5174+ when that
# port is taken. Add your deployed frontend origin here too once you have one.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

FEEDBACK_LOG = Path("./feedback.jsonl")

# Retriever/reranker/LLM client are expensive to construct (model loads, API
# clients) — build them lazily on first use and cache on app.state instead of
# at import time, so `python -m ingest.pipeline` etc. don't pay that cost.
_retriever: HybridRetriever | None = None


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        try:
            _retriever = HybridRetriever()
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Search index not built yet: {e}. Call POST /ingest/run first.",
            ) from e
    return _retriever


def invalidate_retriever_cache() -> None:
    """Call after /ingest/run rebuilds the index, so the next /chat request
    picks up the new data instead of the stale in-memory one."""
    global _retriever
    _retriever = None


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------
@app.post("/ingest/upload")
async def ingest_upload(files: list[UploadFile], subfolder: str = "uploaded"):
    safe_subfolder = "".join(c for c in subfolder if c.isalnum() or c in "-_") or "uploaded"
    dest_dir = Path(config.DATA_RAW_DIR) / safe_subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        dest_path = dest_dir / Path(f.filename).name  # strip any path components
        with dest_path.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(str(dest_path))

    return {"saved": saved, "subfolder": safe_subfolder}


@app.post("/ingest/run")
async def ingest_run():
    """Runs load -> chunk -> write, then rebuilds the vector + BM25 index.
    Returns the same parsed/failed/breakdown report the CLI prints."""
    pipeline_report = run_pipeline()
    if pipeline_report["chunks"] == 0:
        return {"pipeline": pipeline_report, "index": None}

    index_report = build_index()
    invalidate_retriever_cache()
    return {"pipeline": pipeline_report, "index": index_report}


@app.get("/sources")
async def list_sources():
    chunks_path = Path(config.DATA_PROCESSED_DIR) / "chunks.jsonl"
    if not chunks_path.exists():
        return {"documents": []}

    docs: dict[str, dict] = {}
    for line in chunks_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        key = c["source_path"]
        if key not in docs:
            docs[key] = {
                "source_path": key,
                "doc_title": c["doc_title"],
                "content_type_seen": set(),
                "chunk_count": 0,
            }
        docs[key]["chunk_count"] += 1
        docs[key]["content_type_seen"].add(c["content_type"])

    for d in docs.values():
        d["content_type_seen"] = sorted(d["content_type_seen"])

    return {"documents": list(docs.values())}


# --------------------------------------------------------------------------
# Chat
# --------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    query: str
    history: list[ChatMessage] = []
    doc_title: str | None = None  # optional metadata filter (Phase 4, step 4)


@app.post("/chat")
async def chat(req: ChatRequest):
    retriever = get_retriever()
    reranker = get_reranker()
    llm_client = get_llm_client()

    history = [m.model_dump() for m in req.history] if req.history else None
    search_kwargs = {"doc_title": req.doc_title} if req.doc_title else {}

    def sse_stream():
        for event in generate_answer(
            req.query, retriever, reranker, llm_client, history=history, **search_kwargs
        ):
            # Trim full chunk text out of the "chunks" event before it goes
            # over the wire during streaming — the frontend gets full chunk
            # detail in the final "done" event's citations instead.
            if event["type"] == "chunks":
                event = {
                    "type": "chunks",
                    "chunks": [
                        {k: v for k, v in c.items() if k != "text"} for c in event["chunks"]
                    ],
                }
            yield f"data: {json.dumps(event)}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(sse_stream(), media_type="text/event-stream")


# --------------------------------------------------------------------------
# Feedback
# --------------------------------------------------------------------------
class FeedbackRequest(BaseModel):
    query: str
    answer: str
    rating: str  # "up" | "down"
    citations: list[dict] = []


@app.post("/feedback")
async def feedback(req: FeedbackRequest):
    if req.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")
    record = req.model_dump()
    record["logged_at"] = datetime.now(timezone.utc).isoformat()
    with FEEDBACK_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"status": "logged"}


@app.get("/health")
async def health():
    return {"status": "ok"}
