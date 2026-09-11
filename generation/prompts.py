"""
Prompt construction (Phase 5 of the plan). The requirements from the plan,
encoded directly into the system prompt:
  - pass retrieved chunks with explicit IDs, ask the model to cite IDs inline
  - answer ONLY from the provided context
  - require an explicit "not enough information" path
"""
from __future__ import annotations

SYSTEM_PROMPT = """\
You are a documentation assistant. You answer questions using ONLY the \
context chunks provided below — never your own outside knowledge.

Each chunk has a citation ID like [1], [2], etc. When you use information \
from a chunk, cite its ID inline immediately after the relevant sentence, \
like this: "Pods enter ImagePullBackOff when the image can't be pulled [2]."

Rules:
- If the context does not contain enough information to answer, say exactly: \
"I don't have enough information in these documents to answer that." Do not \
guess or fill gaps with general knowledge.
- Every factual claim must have at least one citation.
- If chunks disagree, say so and cite both.
- Be concise. Don't repeat the question back.
"""


def build_context_block(chunks: list[dict]) -> str:
    """chunks: reranked retrieval results, already trimmed to top-k. Assigns
    each a 1-indexed citation ID in the order given (so callers should pass
    them already sorted best-first)."""
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        location = chunk.get("doc_title", "unknown source")
        section = chunk.get("section_path")
        if section and section != "(root)":
            location = f"{location} > {section}"
        page = chunk.get("page_number")
        if page:
            location += f" (page {page})"
        parts.append(f"[{i}] Source: {location}\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)


def build_messages(query: str, chunks: list[dict], history: list[dict] | None = None) -> list[dict]:
    context_block = build_context_block(chunks)
    user_content = (
        f"Context:\n\n{context_block}\n\n---\n\nQuestion: {query}"
        if chunks
        else f"Question: {query}\n\n(No relevant context was retrieved for this question.)"
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    return messages
