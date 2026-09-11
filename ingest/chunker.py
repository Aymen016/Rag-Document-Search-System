"""
Structural chunking (Phase 3 of the plan). Naive fixed-size chunking wrecks
technical docs — it slices code blocks and tables in half. This chunker:

1. Splits on heading boundaries (markdown # / ## / ### or a detected heading line)
2. Never splits inside a fenced code block or a markdown table — kept whole
   even if it blows past max_tokens
3. Oversized sections get split on paragraph boundaries with ~15% overlap
4. Every chunk is prefixed with "{doc_title} > {section_path}" so it's
   understandable in isolation — the whole point per the plan's checkpoint:
   "if you can't tell what a chunk is about from the chunk alone, it's wrong."
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ingest.loaders import Document

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^(```|~~~)")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")

# Rough token estimate: ~4 chars/token for English technical prose. Good enough
# for chunk-sizing decisions; swap for a real tokenizer (tiktoken) if you want
# exact counts to match your embedding model's tokenizer.
CHARS_PER_TOKEN = 4


@dataclass
class Chunk:
    text: str  # includes the "{doc_title} > {section_path}" prefix
    source_path: str
    doc_title: str
    section_heading: str
    section_path: str
    page_number: int | None
    chunk_index: int
    content_type: str  # "prose" | "code" | "table" | "mixed"
    metadata: dict = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class _Block:
    """One atomic unit that must never be split: a paragraph, a whole code
    fence, or a whole table."""

    text: str
    kind: str  # "prose" | "code" | "table"


def _split_into_blocks(body: str) -> list[_Block]:
    lines = body.splitlines()
    blocks: list[_Block] = []
    buf: list[str] = []
    i = 0

    def flush_prose():
        if buf and "".join(buf).strip():
            blocks.append(_Block("\n".join(buf), "prose"))
        buf.clear()

    while i < len(lines):
        line = lines[i]

        if FENCE_RE.match(line.strip()):
            flush_prose()
            fence_lines = [line]
            i += 1
            while i < len(lines) and not FENCE_RE.match(lines[i].strip()):
                fence_lines.append(lines[i])
                i += 1
            if i < len(lines):  # closing fence
                fence_lines.append(lines[i])
                i += 1
            blocks.append(_Block("\n".join(fence_lines), "code"))
            continue

        if TABLE_ROW_RE.match(line):
            flush_prose()
            table_lines = [line]
            i += 1
            while i < len(lines) and TABLE_ROW_RE.match(lines[i]):
                table_lines.append(lines[i])
                i += 1
            blocks.append(_Block("\n".join(table_lines), "table"))
            continue

        if line.strip() == "":
            buf.append(line)
            # paragraph boundary once we've accumulated real content
            if buf and any(b.strip() for b in buf[:-1]):
                # peek: is the next non-blank line still prose? if so keep
                # going, we only flush on a genuine blank-line gap already
                # captured above — flush here to get paragraph granularity
                flush_prose()
            i += 1
            continue

        buf.append(line)
        i += 1

    flush_prose()
    return [b for b in blocks if b.text.strip()]


def _split_headings(text: str) -> list[tuple[list[str], str, str]]:
    """Returns [(heading_path, heading_text, section_body), ...]. The whole
    doc before the first heading becomes one section with an empty path."""
    lines = text.splitlines()
    sections: list[tuple[list[str], str, str]] = []
    path_stack: list[tuple[int, str]] = []  # (level, title)

    current_heading = ""
    current_path: list[str] = []
    current_body: list[str] = []
    in_fence = False

    def flush():
        body = "\n".join(current_body).strip()
        if body:
            sections.append((list(current_path), current_heading, body))

    for line in lines:
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            current_body.append(line)
            continue

        m = None if in_fence else HEADING_RE.match(line)
        if m:
            flush()
            level, title = len(m.group(1)), m.group(2).strip()
            path_stack = [p for p in path_stack if p[0] < level]
            path_stack.append((level, title))
            current_path = [t for _, t in path_stack]
            current_heading = title
            current_body = []
        else:
            current_body.append(line)

    flush()

    if not sections:
        # no headings at all -> whole document is one section
        sections = [([], "", text)]
    return sections


def chunk_document(
    doc: Document,
    max_tokens: int = 500,
    overlap_ratio: float = 0.15,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0

    for path_parts, heading, body in _split_headings(doc.text):
        # If the document's H1 doubles as its title (common — see _first_h1
        # in loaders.py), don't repeat it as the first element of every
        # section path: "Deployment Guide > Deployment Guide > Prerequisites"
        # is noise; "Deployment Guide > Prerequisites" is the useful form.
        if path_parts and path_parts[0] == doc.doc_title:
            path_parts = path_parts[1:]
        section_path = " > ".join(path_parts) if path_parts else "(root)"
        blocks = _split_into_blocks(body)

        group: list[_Block] = []
        group_tokens = 0

        def emit(group_blocks: list[_Block]):
            nonlocal idx
            if not group_blocks:
                return
            raw = "\n\n".join(b.text for b in group_blocks)
            kinds = {b.kind for b in group_blocks}
            content_type = kinds.pop() if len(kinds) == 1 else "mixed"
            prefixed = f"{doc.doc_title} > {section_path}\n\n{raw}"
            chunks.append(
                Chunk(
                    text=prefixed,
                    source_path=doc.source_path,
                    doc_title=doc.doc_title,
                    section_heading=heading,
                    section_path=section_path,
                    page_number=doc.metadata.get("page"),
                    chunk_index=idx,
                    content_type=content_type,
                    metadata=dict(doc.metadata),
                )
            )
            idx += 1

        for block in blocks:
            block_tokens = estimate_tokens(block.text)

            # Rule: never split a code block or table, even if it alone
            # exceeds max_tokens — emit it as its own chunk.
            if block.kind in ("code", "table") and block_tokens > max_tokens:
                emit(group)
                group, group_tokens = [], 0
                emit([block])
                continue

            if group_tokens + block_tokens > max_tokens and group:
                emit(group)
                # ~15% overlap: carry the tail of the previous group forward
                overlap_tokens = int(max_tokens * overlap_ratio)
                tail: list[_Block] = []
                tail_tokens = 0
                for b in reversed(group):
                    t = estimate_tokens(b.text)
                    if tail_tokens + t > overlap_tokens:
                        break
                    tail.insert(0, b)
                    tail_tokens += t
                group = [b for b in tail if b.kind == "prose"]  # never re-split code/table into overlap
                group_tokens = sum(estimate_tokens(b.text) for b in group)

            group.append(block)
            group_tokens += block_tokens

        emit(group)

    return chunks
