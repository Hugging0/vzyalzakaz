from __future__ import annotations

from dataclasses import dataclass, field

from app.config import CandidateProfile
from app.schemas import RawOpportunity
from app.services.normalizer import normalize_text

POSITIVE_KEYWORDS = {
    "python",
    "fastapi",
    "automation",
    "automate",
    "workflow",
    "ai automation",
    "ai agent",
    "agents",
    "llm",
    "rag",
    "openai",
    "claude",
    "gemini",
    "deepseek",
    "n8n",
    "make.com",
    "zapier",
    "api",
    "integration",
    "webhook",
    "telegram bot",
    "crm",
    "postgres",
    "scraping",
    "parser",
    "backend",
    "mvp",
    "prototype",
    "internal tool",
    "business automation",
    "report automation",
    "email automation",
    "lead automation",
    "document processing",
    "автоматизация",
    "ии агент",
    "ии-агент",
    "нейросеть",
    "интеграция",
    "бот",
    "telegram",
    "парсер",
    "скрипт",
    "бекенд",
    "внутренний сервис",
    "обработка документов",
    "автоматизация отчетов",
    "برنامه نویس",
    "پایتون",
    "هوش مصنوعی",
    "پروژه",
    "فریلنس",
    "دورکاری",
    "ربات تلگرام",
}

PREFERRED_FORMATS = {
    "freelance",
    "contract",
    "project",
    "fixed price",
    "fixed-price",
    "part-time",
    "part time",
    "async",
    "asynchronous",
    "фриланс",
    "проект",
    "подработка",
    "частичная занятость",
    "неполная занятость",
    "فریلنس",
    "پروژه",
    "دورکاری",
}

NEGATIVE_RULES = {
    "full_time": {
        "full-time",
        "full time",
        "full-time only",
        "full time only",
        "полная занятость",
        "полный день",
        "40 hours/week",
        "40 часов",
    },
    "office": {
        "office only",
        "on-site only",
        "on-site",
        "onsite",
        "in-office",
        "hybrid",
        "только офис",
        "работа в офисе",
        "гибрид",
    },
    "relocation": {"relocation required", "обязательная релокация", "переезд обязателен"},
    "unpaid": {"unpaid internship", "неоплачиваемая стажировка"},
    "commission": {"commission only", "только процент"},
    "spam": {"guaranteed income", "гарантированный доход", "без вложений", "легкие деньги"},
    "gambling": {"casino", "gambling", "казино", "ставки на спорт"},
    "coursework": {"coursework", "homework", "курсовая", "дипломная работа", "домашнее задание"},
    "candidate_profile": {"willing to relocate", "open to relocation"},
}


@dataclass(slots=True)
class PrefilterResult:
    passed: bool
    score: float
    positive_matches: list[str] = field(default_factory=list)
    negative_matches: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def evaluate(raw: RawOpportunity, profile: CandidateProfile) -> PrefilterResult:
    text = normalize_text(f"{raw.title} {raw.description} {raw.raw_text}")
    skills = {normalize_text(skill) for skill in profile.candidate.skills}
    positive = sorted(keyword for keyword in POSITIVE_KEYWORDS | skills if keyword in text)
    formats = sorted(keyword for keyword in PREFERRED_FORMATS if keyword in text)
    negatives: list[str] = []

    for category, phrases in NEGATIVE_RULES.items():
        if category == "coursework" and not profile.avoid.coursework:
            continue
        if any(phrase in text for phrase in phrases):
            negatives.append(category)

    score = min(70.0, len(positive) * 9.0) + min(20.0, len(formats) * 7.0)
    if raw.remote is True:
        score += 8
    if raw.budget_max and raw.currency == "RUB" and raw.budget_max < profile.economics.minimum_project_rub:
        negatives.append("budget_too_low")
    score_penalties = set(negatives)
    if formats:
        score_penalties.discard("full_time")
    score -= len(score_penalties) * 35
    score = max(0.0, min(100.0, score))

    hard_reject = any(
        reason
        in {
            "office",
            "relocation",
            "unpaid",
            "commission",
            "spam",
            "gambling",
            "coursework",
            "candidate_profile",
        }
        for reason in negatives
    )
    if "full_time" in negatives and profile.avoid.full_time and not formats:
        hard_reject = True
    passed = bool(positive) and score >= 18 and not hard_reject
    reasons = [*(f"match:{item}" for item in positive[:8]), *(f"format:{item}" for item in formats[:4])]
    reasons.extend(f"penalty:{item}" for item in sorted(set(negatives)))
    return PrefilterResult(passed, score, positive, sorted(set(negatives)), reasons)
