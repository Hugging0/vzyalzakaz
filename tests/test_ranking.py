from datetime import UTC, datetime, timedelta

from app.services.ranking import freshness_score


def test_freshness_buckets():
    now = datetime.now(UTC)
    assert freshness_score(now - timedelta(minutes=5), now) == 100
    assert freshness_score(now - timedelta(minutes=30), now) == 85
    assert freshness_score(now - timedelta(days=4), now) == 0
