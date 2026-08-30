from datetime import UTC, datetime, timedelta

from app.services.ranking import final_score, freshness_score


def test_freshness_buckets():
    now = datetime.now(UTC)
    assert freshness_score(now - timedelta(minutes=5), now) == 100
    assert freshness_score(now - timedelta(minutes=30), now) == 85
    assert freshness_score(now - timedelta(days=4), now) == 0


def test_weighted_score(profile):
    score = final_score(90, 80, 70, 100, profile.ranking)
    assert score == 83.5
