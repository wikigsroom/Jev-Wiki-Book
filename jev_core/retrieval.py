from __future__ import annotations

import math
import re
import time
from collections import Counter
from urllib.parse import urlencode

from .common import query_tokens, tokens
from .parsing import passages


class Retriever:
    def __init__(self, snapshot: dict):
        self.snapshot = snapshot
        self.items = [part for block in snapshot["blocks"] if block["text"] for part in passages(block)]
        self.counts = [Counter(tokens(part["text"])) for part in self.items]
        self.lengths = [max(1, sum(c.values())) for c in self.counts]
        self.average = sum(self.lengths) / len(self.lengths) if self.lengths else 1
        self.postings = {}
        for index, count in enumerate(self.counts):
            for term, frequency in count.items():
                self.postings.setdefault(term, {})[index] = frequency

    def search(self, question: str, top_k: int) -> list[dict]:
        terms = Counter(query_tokens(question))
        scores = {}
        query_weights = {term: math.log(1 + (len(self.items) + 0.5) / (len(self.postings.get(term, {})) + 0.5)) for term in terms}
        total_weight = sum(query_weights.values()) or 1
        for term, query_frequency in terms.items():
            posting = self.postings.get(term, {})
            idf = math.log(1 + (len(self.items) - len(posting) + 0.5) / (len(posting) + 0.5))
            for index, frequency in posting.items():
                denominator = frequency + 1.45 * (0.28 + 0.72 * self.lengths[index] / self.average)
                scores[index] = scores.get(index, 0) + idf * frequency * 2.45 / denominator * min(query_frequency, 2)
        ranked = sorted(scores, key=lambda index: (-scores[index], index))[:top_k]
        result = []
        for rank, index in enumerate(ranked, 1):
            item = dict(self.items[index])
            matched = set(terms) & self.counts[index].keys()
            coverage = sum(query_weights[term] for term in matched) / total_weight
            item.update(retrieval_score=round(scores[index], 5), retrieval_rank=rank,
                        query_coverage=round(coverage, 5), matched_terms=sorted(matched, key=len, reverse=True),
                        chunk_id=f"{item['block_id']}:{item['char_start']}-{item['char_end']}",
                        paragraph_number=item["locator"].get("paragraph_number"),
                        paragraph_index=(item["locator"]["paragraph_number"] - 1) if item["locator"].get("paragraph_number") else None)
            result.append(item)
        return result


def select_evidence(evaluated: list[dict], limit: int) -> list[dict]:
    """Do not turn every ranked candidate into evidence. Choice scores are not calibrated confidence."""
    best_coverage = max((item["query_coverage"] for item in evaluated), default=0)
    # Conservative literal support: avoid filling the result limit with passages
    # that merely mention the same topic. These gates are heuristics, not certainty.
    minimum_coverage = max(0.30, best_coverage * 0.85)
    accepted = [item for item in evaluated if item["jev"]["supports_over_none"]
                and item["jev"]["choice"] != "none" and item["query_coverage"] >= minimum_coverage
                and len(item["matched_terms"]) >= 1]
    # Rank fusion avoids comparing softmax probabilities from different candidate sets.
    for item in accepted:
        batch_peers = [other for other in evaluated if other["jev"]["batch"] == item["jev"]["batch"]]
        model_rank = 1 + sum(other["jev"]["probability"] > item["jev"]["probability"] for other in batch_peers)
        # The released game checkpoint is not a trained document reranker. Keep
        # BM25 dominant; local NanoJev refines the order among supported passages.
        item["fusion_score"] = 1 / (1 + item["retrieval_rank"]) + 0.25 / (1 + model_rank)
    accepted.sort(key=lambda item: (-item["fusion_score"], item["retrieval_rank"]))
    picked, seen = [], set()
    for item in accepted:
        # Keep the strongest part of a long paragraph and suppress exact repeated quotes.
        fingerprint = re.sub(r"\s+", "", item["text"])
        if item["block_id"] in seen or fingerprint in seen:
            continue
        seen.update((item["block_id"], fingerprint))
        picked.append(item)
        if len(picked) >= limit:
            break
    return picked


class RagService:
    def __init__(self, store, model):
        self.store = store
        self.model = model

    def query(self, question: str, top_k: int = 12, max_evidence: int = 3, library_id=None) -> dict:
        started = time.perf_counter()
        snapshot = self.store.snapshot(library_id)
        retriever = Retriever(snapshot)
        candidates = retriever.search(question, top_k)
        evaluated = self.model.rank(question, candidates) if candidates else []
        evidence = select_evidence(evaluated, max_evidence)
        status = "found" if evidence else "no_answer" if snapshot["blocks"] else "empty"
        citations = []
        for index, item in enumerate(evidence, 1):
            query = urlencode({"library_id": snapshot["library_id"], "generation": snapshot["generation"]})
            item.update(citation_id=f"S{index}", route="local_jev_evidence", generation=snapshot["generation"],
                        source_url=f"/api/documents/{item['document_id']}?{query}",
                        raw_url=f"/api/documents/{item['document_id']}/raw?{query}")
            citations.append({"id": f"S{index}", "document_id": item["document_id"], "document_name": item["document_name"],
                              "block_id": item["block_id"], "chunk_id": item["chunk_id"], "locator": item["locator"],
                              "text": item["text"], "char_start": item["char_start"], "char_end": item["char_end"],
                              "library_id": snapshot["library_id"], "generation": snapshot["generation"],
                              "source_url": item["source_url"], "raw_url": item["raw_url"]})
        message = {"empty": "当前目录尚未建立可检索索引，请扫描目录或导入文档。",
                   "no_answer": "未找到足以回答这个问题的原文。可以换用文档中的名称或关键词，或检查文档是否已导入。"}
        answer = "\n\n".join(f"[{item['citation_id']}] {item['document_name']} · {item['locator']['label']}\n{item['text']}" for item in evidence) if evidence else message[status]
        return {"question": question, "status": status, "answer": answer, "answer_provider": "original-text-only",
                "decision_mode": "local-nanojev", "library_id": snapshot["library_id"], "generation": snapshot["generation"],
                "source_root": snapshot["source_root"], "evidence": evidence, "citations": citations,
                "diagnostics": {"retrieval_candidates": len(candidates), "local_jev_evaluated": len(evaluated),
                    "evidence_count": len(evidence), "rejected_count": len(evaluated) - len(evidence),
                    "latency_ms": round((time.perf_counter() - started) * 1000), "model": self.model.status(),
                    "ranking": "BM25-dominant reciprocal rank + 0.25 local NanoJev within-batch rank; none and lexical coverage gates",
                    "probabilities_are_calibrated": False, "network_policy": "local files only; no provider API client"}}
