"""
Ties retrieval + generation together with the guardrails from Phase 5:

  - If the top reranker score is below CONFIDENCE_THRESHOLD, don't call the
    LLM at all — return the "no confident answer" response immediately.
  - After generation, verify every citation ID the model returned actually
    exists in the context that was sent. Drop/flag hallucinated ones rather
    than silently trusting the model.
  - Stream token-by-token so the UI feels fast.

Used by api/main.py's /chat endpoint and by eval/run_eval.py (non-streamed,
via answer_once).
"""
from __future__ import annotations

import re
from collections.abc import Iterator

import config
from generation.prompts import build_messages

CITATION_RE = re.compile(r"\[(\d+)\]")

NO_CONFIDENT_ANSWER = (
    "I don't have enough information in these documents to answer that."
)


def _top_score(chunks: list[dict]) -> float:
    if not chunks:
        return 0.0
    # rerank_score if the chunk went through the reranker, else fall back to
    # the raw fused retrieval score.
    top = chunks[0]
    return top.get("rerank_score", top.get("fused_score", 0.0))


def extract_cited_ids(text: str) -> list[int]:
    return sorted({int(m) for m in CITATION_RE.findall(text)})


def verify_citations(text: str, chunks: list[dict]) -> dict:
    """Returns which cited IDs are valid (exist in the 1-indexed chunk list
    that was actually sent to the model) vs. hallucinated."""
    cited = extract_cited_ids(text)
    valid_ids = set(range(1, len(chunks) + 1))
    valid = [i for i in cited if i in valid_ids]
    hallucinated = [i for i in cited if i not in valid_ids]
    citations = [
        {
            "id": i,
            "doc_title": chunks[i - 1].get("doc_title"),
            "section_path": chunks[i - 1].get("section_path"),
            "source_path": chunks[i - 1].get("source_path"),
            "page_number": chunks[i - 1].get("page_number"),
            "text": chunks[i - 1].get("text"),
        }
        for i in valid
    ]
    return {"citations": citations, "hallucinated_ids": hallucinated}


def retrieve_and_rerank(query: str, retriever, reranker, **search_kwargs) -> list[dict]:
    candidates = retriever.search(query, top_k=config.RETRIEVAL_TOP_K, **search_kwargs)
    return reranker.rerank(query, candidates, top_k=config.RERANK_TOP_K)


def generate_answer(
    query: str,
    retriever,
    reranker,
    llm_client,
    history: list[dict] | None = None,
    **search_kwargs,
) -> Iterator[dict]:
    """Yields SSE-friendly event dicts:
      {"type": "chunks", "chunks": [...]}          - once, after retrieval
      {"type": "token", "text": "..."}              - many, as the LLM streams
      {"type": "done", "citations": [...], "hallucinated_ids": [...], "text": "..."}
      {"type": "refused", "reason": "low_confidence"}  - instead of the above,
                                                          if the guardrail trips
    """
    chunks = retrieve_and_rerank(query, retriever, reranker, **search_kwargs)
    yield {"type": "chunks", "chunks": chunks}

    if _top_score(chunks) < config.CONFIDENCE_THRESHOLD:
        yield {"type": "refused", "reason": "low_confidence", "text": NO_CONFIDENT_ANSWER}
        return

    messages = build_messages(query, chunks, history=history)
    full_text = []
    for token in llm_client.stream(messages):
        full_text.append(token)
        yield {"type": "token", "text": token}

    text = "".join(full_text)
    verification = verify_citations(text, chunks)
    yield {"type": "done", "text": text, **verification}


def answer_once(query: str, retriever, reranker, llm_client, **search_kwargs) -> dict:
    """Non-streaming convenience wrapper — used by eval/run_eval.py, which
    just needs the final result, not token-by-token events."""
    chunks_used: list[dict] = []
    text = ""
    result = {"refused": False}
    for event in generate_answer(query, retriever, reranker, llm_client, **search_kwargs):
        if event["type"] == "chunks":
            chunks_used = event["chunks"]
        elif event["type"] == "refused":
            result["refused"] = True
            text = event["text"]
        elif event["type"] == "done":
            text = event["text"]
            result["citations"] = event["citations"]
            result["hallucinated_ids"] = event["hallucinated_ids"]
    result["text"] = text
    result["retrieved_chunks"] = chunks_used
    return result
