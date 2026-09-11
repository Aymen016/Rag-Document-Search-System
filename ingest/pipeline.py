"""
Orchestrates load -> chunk -> write. Run it directly:

    python -m ingest.pipeline

Per the plan's Rule: never silently swallow an exception. Every failed file
is logged to ingest_errors.log with a reason, and the run ends with a report:
N parsed, N failed, breakdown by reason. In a real client engagement,
"which 40 of your 5000 docs failed and why" is a question you *will* be asked.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import config
from ingest.chunker import chunk_document
from ingest.loaders import LOADERS, Document, LoaderError, now_iso


def iter_source_files(raw_dir: Path):
    for path in sorted(raw_dir.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            yield path


def load_one(path: Path) -> list[Document]:
    loader = LOADERS.get(path.suffix.lower())
    if loader is None:
        raise LoaderError(f"no loader registered for extension '{path.suffix}'")
    return loader(path)


def run(
    raw_dir: str | None = None,
    processed_dir: str | None = None,
    error_log: str | None = None,
) -> dict:
    raw_dir = Path(raw_dir or config.DATA_RAW_DIR)
    processed_dir = Path(processed_dir or config.DATA_PROCESSED_DIR)
    error_log_path = Path(error_log or config.INGEST_ERROR_LOG)
    processed_dir.mkdir(parents=True, exist_ok=True)

    if not raw_dir.exists():
        print(f"No such raw dir: {raw_dir}. Nothing to ingest.", file=sys.stderr)
        return {"parsed": 0, "failed": 0, "chunks": 0}

    files = list(iter_source_files(raw_dir))
    parsed, failed = 0, 0
    failure_reasons: Counter[str] = Counter()
    seen_hashes: dict[str, str] = {}  # content_hash -> first source_path
    duplicate_count = 0
    total_chunks = 0

    out_path = processed_dir / "chunks.jsonl"
    errors: list[str] = []

    with out_path.open("w", encoding="utf-8") as out_f:
        for path in files:
            try:
                documents = load_one(path)
            except LoaderError as e:
                failed += 1
                reason = str(e)
                failure_reasons[_reason_bucket(reason)] += 1
                errors.append(f"{now_iso()}\t{path}\t{reason}")
                continue
            except Exception as e:  # noqa: BLE001 - deliberately broad: log, don't crash
                failed += 1
                failure_reasons["unexpected_error"] += 1
                errors.append(f"{now_iso()}\t{path}\tunexpected: {e!r}")
                continue

            for doc in documents:
                content_hash = doc.content_hash()
                if content_hash in seen_hashes:
                    duplicate_count += 1
                    doc.metadata["duplicate_of"] = seen_hashes[content_hash]
                else:
                    seen_hashes[content_hash] = doc.source_path

                doc.metadata["ingested_at"] = now_iso()
                doc.metadata["content_hash"] = content_hash

                chunks = chunk_document(
                    doc,
                    max_tokens=config.MAX_CHUNK_TOKENS,
                    overlap_ratio=config.CHUNK_OVERLAP_RATIO,
                )
                for chunk in chunks:
                    out_f.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
                total_chunks += len(chunks)

            parsed += 1

    if errors:
        with error_log_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(errors) + "\n")

    report = {
        "parsed": parsed,
        "failed": failed,
        "duplicates_flagged": duplicate_count,
        "chunks": total_chunks,
        "failure_breakdown": dict(failure_reasons),
        "output": str(out_path),
        "error_log": str(error_log_path) if errors else None,
    }
    _print_report(report)
    return report


def _reason_bucket(reason: str) -> str:
    reason_l = reason.lower()
    if "empty" in reason_l:
        return "empty_file"
    if "non-utf8" in reason_l or "decode" in reason_l:
        return "encoding_error"
    if "scanned" in reason_l or "ocr" in reason_l:
        return "scanned_no_text"
    if "corrupt" in reason_l or "unreadable" in reason_l:
        return "corrupt_file"
    if "no loader" in reason_l:
        return "unsupported_format"
    if "not installed" in reason_l:
        return "missing_dependency"
    return "other"


def _print_report(report: dict) -> None:
    print("\n=== Ingestion report ===")
    print(f"  Parsed:  {report['parsed']}")
    print(f"  Failed:  {report['failed']}")
    print(f"  Duplicates flagged: {report['duplicates_flagged']}")
    print(f"  Chunks written: {report['chunks']} -> {report['output']}")
    if report["failure_breakdown"]:
        print("  Failure breakdown:")
        for reason, count in sorted(
            report["failure_breakdown"].items(), key=lambda kv: -kv[1]
        ):
            print(f"    {reason}: {count}")
        print(f"  Details logged to: {report['error_log']}")
    print("========================\n")


if __name__ == "__main__":
    run()
