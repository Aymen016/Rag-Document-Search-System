"""
Format-specific parsers. Every loader returns a list of Document objects sharing
the same shape, no matter how messy the source format is — that's the contract
the rest of the pipeline depends on.

Add a new format by writing one function here (load_<format>) and registering it
in LOADERS at the bottom.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


@dataclass
class Document:
    text: str
    source_path: str
    doc_title: str
    metadata: dict = field(default_factory=dict)
    # populated by pipeline.py, not the loaders:
    #   format, page (optional), ingested_at, content_hash

    def content_hash(self) -> str:
        """Used by pipeline.py to flag near-duplicate documents."""
        return hashlib.sha256(self.text.encode("utf-8", errors="ignore")).hexdigest()


class LoaderError(Exception):
    """Raised by a loader when a file can't be parsed. Caught by pipeline.py,
    which logs it and moves on — never let one bad file kill the run."""


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------
def load_markdown(path: Path) -> list[Document]:
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError as e:
        raise LoaderError(f"non-utf8 markdown file: {e}") from e

    if not text.strip():
        raise LoaderError("empty file")

    title = _first_h1(text) or path.stem
    return [
        Document(
            text=text,
            source_path=str(path),
            doc_title=title,
            metadata={"format": "markdown"},
        )
    ]


def _first_h1(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


# --------------------------------------------------------------------------
# Plain text
# --------------------------------------------------------------------------
def load_text(path: Path) -> list[Document]:
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError as e:
        raise LoaderError(f"non-utf8 text file: {e}") from e
    if not text.strip():
        raise LoaderError("empty file")
    return [
        Document(
            text=text,
            source_path=str(path),
            doc_title=path.stem,
            metadata={"format": "text"},
        )
    ]


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------
def load_html(path: Path) -> list[Document]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise LoaderError("beautifulsoup4 not installed") from e

    try:
        raw = path.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError as e:
        raise LoaderError(f"non-utf8 html file: {e}") from e

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()

    title_tag = soup.find("title") or soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else path.stem

    text = soup.get_text("\n", strip=True)
    if not text.strip():
        raise LoaderError("no extractable text (script-rendered page?)")

    return [
        Document(
            text=text,
            source_path=str(path),
            doc_title=title,
            metadata={"format": "html"},
        )
    ]


# --------------------------------------------------------------------------
# PDF — the messiest format: multi-column layout, tables, scanned pages
# --------------------------------------------------------------------------
def load_pdf(path: Path) -> list[Document]:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise LoaderError("pymupdf not installed") from e

    try:
        doc = fitz.open(path)
    except Exception as e:
        raise LoaderError(f"corrupt or unreadable PDF: {e}") from e

    if doc.page_count == 0:
        raise LoaderError("PDF has zero pages")

    documents: list[Document] = []
    no_text_pages = 0

    for page_num, page in enumerate(doc, start=1):
        # "blocks" mode + sort roughly handles multi-column layout: PyMuPDF
        # returns text blocks with bounding boxes, which we sort top-to-bottom,
        # left-to-right instead of trusting raw extraction order.
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (round(b[1] / 20), b[0]))  # bucket by row, then x
        page_text = "\n".join(b[4].strip() for b in blocks if b[4].strip())

        if not page_text.strip():
            no_text_pages += 1
            continue  # likely a scanned image page — see note below

        documents.append(
            Document(
                text=page_text,
                source_path=str(path),
                doc_title=path.stem,
                metadata={"format": "pdf", "page": page_num},
            )
        )

    doc.close()

    if not documents:
        # Every page had no extractable text -> this is a scanned PDF.
        # Decision point from the plan: OCR or skip-and-log. We skip and log
        # loudly rather than silently dropping it — OCR is a deliberate
        # opt-in (wire in `pytesseract` here if/when you need it).
        raise LoaderError(
            f"no extractable text on any of {doc.page_count} pages "
            f"(likely scanned images — needs OCR, not implemented yet)"
        )
    if no_text_pages:
        # Partial-text PDF: some pages parsed, some didn't. Don't raise —
        # this file still produced usable documents — but the pipeline's
        # summary report should surface this count.
        documents[0].metadata["pages_without_text"] = no_text_pages

    return documents


# --------------------------------------------------------------------------
# CSV (e.g. spreadsheet-exported FAQs)
# --------------------------------------------------------------------------
def load_csv(path: Path) -> list[Document]:
    try:
        with path.open(newline="", encoding="utf-8", errors="strict") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except UnicodeDecodeError as e:
        raise LoaderError(f"non-utf8 csv file: {e}") from e
    except csv.Error as e:
        raise LoaderError(f"malformed csv: {e}") from e

    if not rows:
        raise LoaderError("csv has no data rows")

    documents = []
    for i, row in enumerate(rows):
        # Treat each row as its own small document — natural fit for FAQ-style
        # CSVs where each row already is one question/answer unit.
        text = "\n".join(f"{k}: {v}" for k, v in row.items() if v)
        if not text.strip():
            continue
        documents.append(
            Document(
                text=text,
                source_path=str(path),
                doc_title=f"{path.stem} (row {i + 1})",
                metadata={"format": "csv", "row": i + 1},
            )
        )

    if not documents:
        raise LoaderError("csv rows were all empty")
    return documents


# --------------------------------------------------------------------------
# JSON / JSONL (e.g. Stack Exchange–style Q&A dumps once extracted)
# --------------------------------------------------------------------------
def load_jsonl(path: Path) -> list[Document]:
    documents = []
    try:
        with path.open(encoding="utf-8", errors="strict") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    raise LoaderError(f"bad JSON on line {line_num}: {e}") from e
                text = obj.get("text") or obj.get("body") or obj.get("answer") or ""
                title = obj.get("title") or f"{path.stem} (line {line_num})"
                if not text.strip():
                    continue
                documents.append(
                    Document(
                        text=text,
                        source_path=str(path),
                        doc_title=title,
                        metadata={"format": "jsonl", "line": line_num},
                    )
                )
    except UnicodeDecodeError as e:
        raise LoaderError(f"non-utf8 jsonl file: {e}") from e

    if not documents:
        raise LoaderError("jsonl produced no usable documents")
    return documents


# --------------------------------------------------------------------------
# Registry — pipeline.py routes by file extension through this dict
# --------------------------------------------------------------------------
LOADERS: dict[str, Callable[[Path], list[Document]]] = {
    ".md": load_markdown,
    ".markdown": load_markdown,
    ".txt": load_text,
    ".rst": load_text,
    ".html": load_html,
    ".htm": load_html,
    ".pdf": load_pdf,
    ".csv": load_csv,
    ".jsonl": load_jsonl,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
