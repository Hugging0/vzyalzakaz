from __future__ import annotations

from datetime import UTC, datetime

from app.config import Ranking


def freshness_score(published_at: datetime | None, now: datetime | None = None) -> float:
    if published_at is None:
        return 0
    now = now or datetime.now(UTC)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    minutes = max(0, (now - published_at).total_seconds() / 60)
    if minutes < 15:
        return 100
    if minutes < 60:
        return 85
    if minutes < 180:
        return 70
    if minutes < 720:
        return 55
    if minutes < 1440:
        return 40
    if minutes <= 4320:
        return 20
    return 0


def final_score(fit: float, money: float, win: float, freshness: float, config: Ranking) -> float:
    weights = [config.fit_weight, config.money_weight, config.win_weight, config.freshness_weight]
    denominator = sum(weights) or 1
    result = (
        fit * config.fit_weight
        + money * config.money_weight
        + win * config.win_weight
        + freshness * config.freshness_weight
    ) / denominator
    return round(max(0.0, min(100.0, result)), 2)
