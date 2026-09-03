from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.services.retrieval import lexical_similarity


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    vertical: str
    precision_at_10: float
    recall_at_10: float
    false_negative_rate_at_10: float
    cross_vertical_false_positives: int
    adjacent_misses: tuple[str, ...]


def evaluate_corpus(path: Path) -> list[RetrievalMetrics]:
    """Run the network-free fallback regression corpus.

    This is a compact engineering guardrail, not a production-quality relevance benchmark.
    """
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    results = []
    for scenario in payload["scenarios"]:
        ranked = sorted(
            scenario["opportunities"],
            key=lambda item: lexical_similarity(scenario["profile"], item["text"]),
            reverse=True,
        )
        top = ranked[:10]
        relevant = {item["id"] for item in ranked if item["relevant"]}
        found = {item["id"] for item in top if item["relevant"]}
        adjacent = {item["id"] for item in ranked if item.get("adjacent")}
        recall = len(found) / max(len(relevant), 1)
        results.append(
            RetrievalMetrics(
                vertical=scenario["id"],
                precision_at_10=len(found) / max(len(top), 1),
                recall_at_10=recall,
                false_negative_rate_at_10=1 - recall,
                cross_vertical_false_positives=sum(
                    not item["relevant"] for item in top
                ),
                adjacent_misses=tuple(sorted(adjacent - found)),
            )
        )
    return results
