from __future__ import annotations

from app.config import PortfolioProject
from app.services.normalizer import normalize_text


def select_portfolio(text: str, projects: list[PortfolioProject]) -> PortfolioProject | None:
    normalized = normalize_text(text)
    tokens = set(normalized.split())
    best: tuple[float, PortfolioProject] | None = None
    for project in projects:
        skills = {normalize_text(skill) for skill in project.skills}
        phrase_matches = sum(2 for skill in skills if skill and skill in normalized)
        token_matches = len(tokens & set(" ".join(skills).split()))
        score = phrase_matches + token_matches
        if best is None or score > best[0]:
            best = (score, project)
    return best[1] if best and best[0] > 0 else None
