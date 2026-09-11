"""
Evaluation harness (Phase 7 of the plan) — this is the part that separates
this project from a tutorial RAG demo. Measures retrieval and generation
*separately*, and reproduces the plan's progression table:

    vector-only baseline -> hybrid (BM25 + vector) -> hybrid + rerank

Run it:
    python -m eval.run_eval                       # full progression, all stages
    python -m eval.run_eval --stage reranked       # just the final stage
    python -m eval.run_eval --testset path/to.json

Writes eval/results.json (per-question + per-stage summary) and prints the
same table to stdout — paste it straight into the README per the plan's
write-up checklist.

NOTE: the correctness/citation-accuracy checks here are deliberately simple
(keyword overlap, substring match) so they run for free with no extra API
calls. Swap in an LLM-as-judge call or `ragas` for less brittle scoring once
you've got the basics working — see the _answer_correctness docstring.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from generation.answer import answer_once
from generation.llm_client import get_llm_client
from retrieval.rerank import get_reranker
from retrieval.search import HybridRetriever

STAGES = {
    "vector_only": {"use_vector": True, "use_bm25": False, "rerank": False},
    "hybrid": {"use_vector": True, "use_bm25": True, "rerank": False},
    "reranked": {"use_vector": True, "use_bm25": True, "rerank": True},
}


def _load_testset(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["questions"]


def _reciprocal_rank(gold_substrings: list[str], ranked_chunks: list[dict]) -> tuple[int, float]:
    """Returns (recall_hit, reciprocal_rank). With no gold substrings (an
    unanswerable question has none by design), both are 0 — retrieval isn't
    scored on those, only refusal is."""
    if not gold_substrings:
        return 0, 0.0
    for rank, chunk in enumerate(ranked_chunks, start=1):
        source = chunk.get("source_path", "")
        if any(sub in source for sub in gold_substrings):
            return 1, 1.0 / rank
    return 0, 0.0


def _answer_correctness(gold_keywords: list[str], answer_text: str) -> bool:
    """Crude, free stand-in for LLM-as-judge: every gold keyword must appear
    (case-insensitive) somewhere in the answer. Good enough to catch a
    completely wrong or empty answer; not good enough to catch subtle
    factual errors — note that honestly in your README rather than
    overselling this number."""
    if not gold_keywords:
        return True
    text_l = answer_text.lower()
    return all(kw.lower() in text_l for kw in gold_keywords)


def evaluate_stage(stage_name: str, questions: list[dict], top_k_retrieval: int, top_k_rerank: int) -> dict:
    stage_cfg = STAGES[stage_name]
    retriever = HybridRetriever()
    reranker = get_reranker() if stage_cfg["rerank"] else None
    llm_client = get_llm_client()

    per_question = []
    for q in questions:
        candidates = retriever.search(
            q["question"],
            top_k=top_k_retrieval,
            use_vector=stage_cfg["use_vector"],
            use_bm25=stage_cfg["use_bm25"],
        )
        ranked_for_scoring = candidates
        if stage_cfg["rerank"]:
            ranked_for_scoring = reranker.rerank(q["question"], candidates, top_k=top_k_rerank)

        recall_hit, rr = _reciprocal_rank(q["gold_source_substrings"], ranked_for_scoring)

        # Generation is only run once per question (on the final "reranked"
        # stage) since it's the expensive/paid part — retrieval-only stages
        # (vector_only, hybrid) just measure Recall@k / MRR.
        result_row = {
            "id": q["id"],
            "category": q["category"],
            "recall_hit": recall_hit,
            "reciprocal_rank": rr,
        }

        if stage_cfg["rerank"]:
            answer = answer_once(q["question"], retriever, reranker, llm_client)
            correctness = _answer_correctness(q["gold_answer_keywords"], answer["text"])
            citation_ids = [c["id"] for c in answer.get("citations", [])]
            hallucinated = answer.get("hallucinated_ids", [])
            citation_accuracy = (
                1.0 if citation_ids and not hallucinated else (0.0 if citation_ids else None)
            )
            correct_refusal = (
                answer["refused"] if not q["expected_answerable"] else not answer["refused"]
            )
            result_row.update(
                {
                    "answer": answer["text"],
                    "refused": answer["refused"],
                    "expected_answerable": q["expected_answerable"],
                    "correct_refusal_behavior": correct_refusal,
                    "answer_correctness": correctness,
                    "citation_accuracy": citation_accuracy,
                    "hallucinated_citation_ids": hallucinated,
                }
            )

        per_question.append(result_row)

    n = len(per_question)
    summary = {
        "stage": stage_name,
        "n_questions": n,
        "recall_at_k": sum(r["recall_hit"] for r in per_question) / n if n else 0.0,
        "mrr": sum(r["reciprocal_rank"] for r in per_question) / n if n else 0.0,
    }
    if stage_cfg["rerank"]:
        answerable = [r for r in per_question if r.get("expected_answerable")]
        unanswerable = [r for r in per_question if r.get("expected_answerable") is False]
        cited_rows = [r for r in per_question if r.get("citation_accuracy") is not None]
        summary.update(
            {
                "answer_correctness": (
                    sum(r["answer_correctness"] for r in answerable) / len(answerable)
                    if answerable
                    else None
                ),
                "citation_accuracy": (
                    sum(r["citation_accuracy"] for r in cited_rows) / len(cited_rows)
                    if cited_rows
                    else None
                ),
                "refusal_accuracy_unanswerable": (
                    sum(r["correct_refusal_behavior"] for r in unanswerable) / len(unanswerable)
                    if unanswerable
                    else None
                ),
                "refusal_accuracy_answerable": (
                    sum(r["correct_refusal_behavior"] for r in answerable) / len(answerable)
                    if answerable
                    else None
                ),
            }
        )

    return {"summary": summary, "per_question": per_question}


def print_progression_table(stage_results: dict[str, dict]) -> None:
    print("\n=== Retrieval/Generation progression ===")
    print(f"{'stage':<12} {'recall@k':>9} {'mrr':>7} {'ans_correct':>12} {'cite_acc':>9} {'refusal_acc':>12}")
    for name, res in stage_results.items():
        s = res["summary"]

        def fmt(v):
            return f"{v:.2f}" if isinstance(v, (int, float)) else "-"

        refusal = s.get("refusal_accuracy_unanswerable")
        print(
            f"{name:<12} {fmt(s['recall_at_k']):>9} {fmt(s['mrr']):>7} "
            f"{fmt(s.get('answer_correctness')):>12} {fmt(s.get('citation_accuracy')):>9} "
            f"{fmt(refusal):>12}"
        )
    print("==========================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--testset", type=str, default="eval/testset.json")
    parser.add_argument("--stage", choices=list(STAGES) + ["all"], default="all")
    parser.add_argument("--top-k-retrieval", type=int, default=25)
    parser.add_argument("--top-k-rerank", type=int, default=5)
    parser.add_argument("--out", type=str, default="eval/results.json")
    args = parser.parse_args()

    questions = _load_testset(Path(args.testset))
    stages_to_run = list(STAGES) if args.stage == "all" else [args.stage]

    all_results = {}
    for stage_name in stages_to_run:
        print(f"Running stage: {stage_name} ...")
        all_results[stage_name] = evaluate_stage(
            stage_name, questions, args.top_k_retrieval, args.top_k_rerank
        )

    Path(args.out).write_text(json.dumps(all_results, indent=2))
    print(f"Wrote detailed results to {args.out}")
    print_progression_table(all_results)
