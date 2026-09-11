"""
Hybrid search (Phase 4 of the plan): BM25 keyword search + vector similarity,
combined with Reciprocal Rank Fusion. This matters a lot for technical docs —
exact strings like `ImagePullBackOff` or `getUserById()` are often missed by
pure semantic search but are exactly what BM25 is good at.

Build the index:      python -m retrieval.search --build
Try a query:           python -m retrieval.search --query "how do I fix ImagePullBackOff"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import re
from pathlib import Path

import config
from retrieval.embeddings import get_embedder

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> list[str]:
    """Deliberately simple: lowercase, split on non-alnum. Keeps identifiers
    like getUserById / ImagePullBackOff as single tokens, which is what makes
    BM25 good at catching exact technical strings that embeddings blur."""
    return [t.lower() for t in TOKEN_RE.findall(text)]


def chunk_id(chunk: dict) -> str:
    # chunk_index restarts at 0 for every Document, and one file can yield many
    # Documents (a CSV row each, a PDF page each) that all share source_path —
    # so source_path + chunk_index is not unique. Hash the text in too.
    key = f"{chunk['source_path']}::{chunk['chunk_index']}::{chunk['text']}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _bm25_path(persist_dir: Path) -> Path:
    return persist_dir / "bm25_index.pkl"


def build_index(
    chunks_path: str | None = None,
    persist_dir: str | None = None,
    collection_name: str = "rag_chunks",
) -> dict:
    import chromadb

    chunks_path = Path(chunks_path or Path(config.DATA_PROCESSED_DIR) / "chunks.jsonl")
    persist_dir = Path(persist_dir or config.CHROMA_PERSIST_DIR)
    persist_dir.mkdir(parents=True, exist_ok=True)

    if not chunks_path.exists():
        raise FileNotFoundError(
            f"{chunks_path} not found — run `python -m ingest.pipeline` first"
        )

    chunks = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not chunks:
        raise ValueError(f"{chunks_path} has no chunks")

    embedder = get_embedder()
    client = chromadb.PersistentClient(path=str(persist_dir))
    existing_names = [c.name for c in client.list_collections()]
    if collection_name in existing_names:
        # Rebuild from scratch each run rather than accumulating stale
        # vectors from a previous ingest — Phase 2's incremental
        # re-indexing (stretch goal) is the place to make this additive.
        client.delete_collection(collection_name)
    collection = client.get_or_create_collection(
        name=collection_name, metadata={"hnsw:space": "cosine"}
    )

    ids = [chunk_id(c) for c in chunks]
    texts = [c["text"] for c in chunks]
    metadatas = [_flat_metadata(c) for c in chunks]

    # Two chunks only hash to the same id if source_path + chunk_index + text
    # are all identical — genuine duplicate content (e.g. repeated boilerplate
    # across pages in a book-length PDF). Chroma's upsert rejects a batch
    # outright if it contains duplicate ids, so dedupe first and keep the
    # first occurrence; no searchable content is lost since the text is
    # byte-identical.
    seen: set[str] = set()
    deduped = [
        (i, t, m) for i, t, m in zip(ids, texts, metadatas) if not (i in seen or seen.add(i))
    ]
    ids, texts, metadatas = (list(x) for x in zip(*deduped)) if deduped else ([], [], [])

    # Batch embed + upsert so this scales past a few thousand chunks without
    # holding every vector in memory at once.
    batch_size = 128
    for i in range(0, len(chunks), batch_size):
        batch_texts = texts[i : i + batch_size]
        vectors = embedder.embed(batch_texts)
        collection.upsert(
            ids=ids[i : i + batch_size],
            embeddings=vectors,
            documents=batch_texts,
            metadatas=metadatas[i : i + batch_size],
        )

    # BM25 needs the full tokenized corpus in memory to score against — store
    # it alongside the vector index so search.py can load both together.
    tokenized_corpus = [tokenize(t) for t in texts]
    with _bm25_path(persist_dir).open("wb") as f:
        pickle.dump(
            {"ids": ids, "tokenized_corpus": tokenized_corpus, "chunks": chunks},
            f,
        )

    return {"chunks_indexed": len(chunks), "persist_dir": str(persist_dir)}


def _flat_metadata(chunk: dict) -> dict:
    """Chroma metadata values must be str/int/float/bool — flatten and drop
    anything else (e.g. nested dicts from the loader's original metadata)."""
    flat = {}
    for key in (
        "source_path",
        "doc_title",
        "section_heading",
        "section_path",
        "page_number",
        "chunk_index",
        "content_type",
    ):
        val = chunk.get(key)
        if val is not None:
            flat[key] = val
    meta = chunk.get("metadata") or {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool)):
            flat[f"meta_{k}"] = v
    return flat


class HybridRetriever:
    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str = "rag_chunks",
    ):
        import chromadb

        self.persist_dir = Path(persist_dir or config.CHROMA_PERSIST_DIR)
        client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = client.get_collection(collection_name)
        self.embedder = get_embedder()

        bm25_path = _bm25_path(self.persist_dir)
        if not bm25_path.exists():
            raise FileNotFoundError(
                f"{bm25_path} not found — run `python -m retrieval.search --build` first"
            )
        with bm25_path.open("rb") as f:
            data = pickle.load(f)
        self._bm25_ids = data["ids"]
        self._chunks_by_id = {cid: c for cid, c in zip(data["ids"], data["chunks"])}

        from rank_bm25 import BM25Okapi

        self._bm25 = BM25Okapi(data["tokenized_corpus"])

    def search(
        self,
        query: str,
        top_k: int | None = None,
        doc_title: str | None = None,
        source_path_prefix: str | None = None,
        rrf_k: int = 60,
        use_vector: bool = True,
        use_bm25: bool = True,
    ) -> list[dict]:
        """Metadata filtering (Phase 4, step 4): scope to a doc set via
        doc_title or a source_path prefix (e.g. a version folder under
        data/raw/).

        use_vector/use_bm25 default to hybrid (both on). eval/run_eval.py
        flips them off one at a time to reproduce the plan's Phase 7
        progression table: vector-only baseline -> hybrid -> (+ rerank)."""
        if not use_vector and not use_bm25:
            raise ValueError("at least one of use_vector / use_bm25 must be True")
        top_k = top_k or config.RETRIEVAL_TOP_K

        where = None
        if doc_title:
            where = {"doc_title": doc_title}

        # --- vector search ---
        vector_ranked_ids: list[str] = []
        if use_vector:
            query_vec = self.embedder.embed_query(query)
            vec_result = self.collection.query(
                query_embeddings=[query_vec],
                n_results=min(top_k * 2, len(self._bm25_ids)),  # overfetch, filter below
                where=where,
            )
            vector_ranked_ids = vec_result["ids"][0]

        # --- BM25 search ---
        bm25_ranked_ids: list[str] = []
        if use_bm25:
            bm25_scores = self._bm25.get_scores(tokenize(query))
            bm25_ranked = sorted(
                range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True
            )
            bm25_ranked_ids = [self._bm25_ids[i] for i in bm25_ranked]

        if source_path_prefix:
            vector_ranked_ids = [
                cid
                for cid in vector_ranked_ids
                if self._chunks_by_id[cid]["source_path"].startswith(source_path_prefix)
            ]
            bm25_ranked_ids = [
                cid
                for cid in bm25_ranked_ids
                if self._chunks_by_id[cid]["source_path"].startswith(source_path_prefix)
            ]

        # --- Reciprocal Rank Fusion ---
        fused_scores: dict[str, float] = {}
        for rank, cid in enumerate(vector_ranked_ids[: top_k * 2], start=1):
            fused_scores[cid] = fused_scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
        for rank, cid in enumerate(bm25_ranked_ids[: top_k * 2], start=1):
            fused_scores[cid] = fused_scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)

        ranked_ids = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)[:top_k]

        results = []
        for cid in ranked_ids:
            chunk = dict(self._chunks_by_id[cid])
            chunk["chunk_id"] = cid
            chunk["fused_score"] = fused_scores[cid]
            results.append(chunk)
        return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true", help="(re)build the index from data/processed/chunks.jsonl")
    parser.add_argument("--query", type=str, help="run a test query against the built index")
    parser.add_argument("--top-k", type=int, default=None)
    args = parser.parse_args()

    if args.build:
        report = build_index()
        print(f"Indexed {report['chunks_indexed']} chunks -> {report['persist_dir']}")

    if args.query:
        retriever = HybridRetriever()
        hits = retriever.search(args.query, top_k=args.top_k)
        for i, h in enumerate(hits, start=1):
            print(f"{i}. [{h['fused_score']:.4f}] {h['doc_title']} > {h['section_path']}")
            print(f"   {h['text'][:150]!r}")
