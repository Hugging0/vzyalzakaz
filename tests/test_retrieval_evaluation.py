from pathlib import Path

from app.evaluation.retrieval import evaluate_corpus


def test_offline_retrieval_quality_gate():
    metrics = evaluate_corpus(Path("tests/fixtures/retrieval_evaluation.yaml"))

    assert {item.vertical for item in metrics} == {
        "backend",
        "frontend",
        "design",
        "marketing",
        "video",
        "content",
        "automation",
    }
    assert all(item.precision_at_10 >= 0.80 for item in metrics)
    assert all(item.recall_at_10 == 1 for item in metrics)
    assert all(not item.adjacent_misses for item in metrics)
