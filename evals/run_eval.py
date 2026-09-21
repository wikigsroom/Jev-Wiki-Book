"""Small local corpus regression evaluation. No training or external requests.

Run with --source tests/ui-library for an isolated synthetic example library.
Without --source, read the existing active library without changing it.
All model execution forbids external socket connections.
"""
from __future__ import annotations

import argparse
import gc
import json
import socket
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev_core.common import BASE_DIR, STORAGE_DIR, atomic_json, now
from jev_core.nanojev import LocalNanoJev
from jev_core.parsing import DocumentParser
from jev_core.retrieval import Retriever, select_evidence
from jev_core.storage import KnowledgeStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="storage/evals/example-results.json")
    parser.add_argument("--questions", default="evals/example-questions.json")
    parser.add_argument("--source", type=Path, help="Build an isolated temporary index from this directory")
    args = parser.parse_args()
    def blocked(*args, **kwargs):
        raise RuntimeError("Evaluation forbids network connections")
    socket.socket.connect = blocked
    socket.create_connection = blocked
    workspace = STORAGE_DIR / "eval-work"
    if args.source:
        workspace.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix="jev-eval-", dir=workspace) if args.source else None
    if args.source:
        source = (BASE_DIR / args.source).resolve()
        if not source.is_dir():
            parser.error("--source must name an existing directory")
        store = KnowledgeStore(Path(temporary.name), source, DocumentParser())
        store.build(source, lambda _: None, threading.Event())
    else:
        store = KnowledgeStore(STORAGE_DIR, BASE_DIR, DocumentParser())
    snapshot = store.snapshot()
    retriever = Retriever(snapshot)
    model = LocalNanoJev()
    cases = json.loads((BASE_DIR / args.questions).read_text(encoding="utf-8"))
    if not cases or not any(case.get("gold_text") for case in cases) or not any(not case.get("gold_text") for case in cases):
        parser.error("Question file must contain both answerable and unanswerable examples")
    rows = []
    for case in cases:
        gold = [b["id"] for b in snapshot["blocks"] if case["gold_text"] and case["gold_text"] in b["text"]]
        if case["gold_text"] and not gold:
            raise ValueError(f"Wrong evaluation corpus or changed gold text: {case['id']}")
        start = time.perf_counter()
        candidates = retriever.search(case["question"], 12)
        scored = model.rank(case["question"], candidates) if candidates else []
        picked = select_evidence(scored, 3)
        def ranks(items):
            return [i for i, item in enumerate(items, 1) if item["block_id"] in gold]
        row = {**case, "gold_blocks": gold, "bm25_gold_ranks": ranks(candidates), "final_gold_ranks": ranks(picked),
               "returned_evidence": len(picked), "evaluated": len(scored), "elapsed_ms": round((time.perf_counter() - start) * 1000),
               "selected": [{"id": b["block_id"], "text": b["text"], "kind": b["kind"]} for b in picked],
               "candidates": [{k: b[k] for k in ("block_id", "text", "kind", "retrieval_rank", "query_coverage", "matched_terms", "jev")} for b in scored]}
        rows.append(row)
        print(json.dumps({k:row[k] for k in ("id", "bm25_gold_ranks", "final_gold_ranks", "returned_evidence", "elapsed_ms")}, ensure_ascii=False), flush=True)
        atomic_json(BASE_DIR / args.output, {"partial": True, "rows": rows})
    positive = [r for r in rows if r["gold_text"]]
    negative = [r for r in rows if not r["gold_text"]]
    def hit(field, n):
        return sum(bool(r[field]) and r[field][0] <= n for r in positive) / len(positive)
    metrics = {"answerable_count": len(positive), "unanswerable_count": len(negative),
               "bm25_hit_at_1": hit("bm25_gold_ranks", 1), "bm25_hit_at_3": hit("bm25_gold_ranks", 3),
               "bm25_recall_at_12": hit("bm25_gold_ranks", 12),
               "final_hit_at_1": hit("final_gold_ranks", 1), "final_hit_at_3": hit("final_gold_ranks", 3),
               "final_mrr_at_3": sum(1/r["final_gold_ranks"][0] if r["final_gold_ranks"] else 0 for r in positive)/len(positive),
               "unanswerable_rejection_rate": sum(not r["returned_evidence"] for r in negative)/len(negative),
               "median_latency_ms": statistics.median(r["elapsed_ms"] for r in rows),
               "max_latency_ms": max(r["elapsed_ms"] for r in rows)}
    result = {"partial": False, "evaluated_at": now(), "library_id": snapshot["library_id"],
              "generation": snapshot["generation"], "documents": len(snapshot["documents"]), "blocks": len(snapshot["blocks"]),
              "network_connections_blocked": True, "model": model.status(), "top_k": 12, "max_evidence": 3,
              "limitations": "Small corpus-specific diagnostic sample, not an independent held-out benchmark. No fine-tuning. Hit metrics do not certify every returned passage.",
              "metrics": metrics, "rows": rows}
    atomic_json(BASE_DIR / args.output, result)
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)
    if temporary:
        gc.collect()
        temporary.cleanup()


if __name__ == "__main__":
    main()
