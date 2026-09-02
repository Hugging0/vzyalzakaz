from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import AppSettings, CandidateProfile, PortfolioProject
from app.schemas import ProfileIntake, RawOpportunity
from app.services.llm_client import ChatCompletionClient
from app.services.normalizer import normalize_text

logger = logging.getLogger(__name__)


class CandidateAssistant:
    """Candidate-specific profile and proposal helper; opportunity facts live elsewhere."""

    def __init__(self, settings: AppSettings, profile: CandidateProfile):
        self.settings = settings
        self.profile = profile
        self.llm = ChatCompletionClient(settings)

    async def generate_proposal(
        self, raw: RawOpportunity, analysis: dict[str, Any], portfolio: PortfolioProject | None
    ) -> str:
        if not self.llm.available:
            return self._deterministic_proposal(raw, analysis, portfolio)
        prompt = self._proposal_prompt(raw, analysis, portfolio)
        try:
            result = await self._call_llm(prompt, json_mode=False)
            if isinstance(result, str):
                return result.strip()[:2000]
            return str(result.get("proposal", "")).strip()[:2000]
        except Exception:
            logger.exception("Proposal generation failed; using local template")
            return self._deterministic_proposal(raw, analysis, portfolio)

    async def extract_profile(self, text: str) -> ProfileIntake:
        """Extract only explicit profile facts; the original text remains the source of truth."""
        if self.settings.llm_provider == "disabled" or not self.settings.llm_api_key:
            return _deterministic_profile_intake(text)
        schema = json.dumps(ProfileIntake.model_json_schema(), ensure_ascii=False)
        prompt = f"""
Extract a freelancer profile from the Russian or English text below.
Return only facts stated or unambiguously implied by the author. Never invent experience.
Normalize technology names to their common spelling. Monetary values are in RUB only when
the text explicitly uses rubles, ₽ or RUB. Return only JSON matching this schema: {schema}

Text:
{text[:6000]}
""".strip()
        try:
            return ProfileIntake.model_validate(await self._call_llm(prompt))
        except Exception:
            logger.exception("Profile intake extraction failed; using local extraction")
            return _deterministic_profile_intake(text)

    async def _call_llm(self, prompt: str, json_mode: bool = True) -> dict | str:
        return await self.llm.complete(
            prompt,
            system="You are a precise job opportunity analyst. Never invent facts.",
            json_mode=json_mode,
        )

    def _proposal_prompt(
        self, raw: RawOpportunity, analysis: dict[str, Any], portfolio: PortfolioProject | None
    ) -> str:
        return f"""
Write a personalized proposal in the same language as the opportunity. Length 500-1200 characters.
Do not use generic openings such as "I am an experienced developer". Refer to the concrete task,
suggest a concise implementation approach, mention only genuinely relevant skills and portfolio,
give a realistic next step, and ask 1-2 useful clarification questions. Do not invent experience.

Candidate: {self.profile.candidate.name}
About: {self.profile.candidate.about}
Skills: {", ".join(self.profile.candidate.skills)}
Relevant portfolio: {portfolio.model_dump_json() if portfolio else "none"}
        Analysis: {json.dumps(analysis, ensure_ascii=False)}
Opportunity: {raw.title}\n{(raw.raw_text or raw.description)[:10000]}

Return only the proposal text.
""".strip()

    def _deterministic_proposal(
        self, raw: RawOpportunity, analysis: dict[str, Any], portfolio: PortfolioProject | None
    ) -> str:
        required = analysis.get("required_skills") or []
        skills = ", ".join(required[:4]) or "Python и API-интеграции"
        case = f" Похожий кейс — «{portfolio.title}»: {portfolio.description}" if portfolio else ""
        return (
            f"Здравствуйте! В задаче «{raw.title}» я бы начал с уточнения входных данных и ожидаемого "
            f"результата, затем собрал небольшой рабочий контур и проверил его на реальных сценариях. "
            f"Для реализации подходят {skills}.{case}\n\n"
            "Могу предложить этапы и оценку после короткого уточнения: какие сервисы уже используются "
            "и есть ли доступ к их API? Какой результат будет считаться готовым для первого этапа?"
        )[:1200]


def _deterministic_profile_intake(text: str) -> ProfileIntake:
    normalized = normalize_text(text)
    vocabulary = {
        "Python": ("python", "питон"),
        "JavaScript": ("javascript", "js"),
        "TypeScript": ("typescript", "ts"),
        "React": ("react", "реакт"),
        "Next.js": ("next.js", "nextjs"),
        "Vue": ("vue", "vue.js"),
        "Node.js": ("node.js", "nodejs"),
        "FastAPI": ("fastapi",),
        "Django": ("django", "джанго"),
        "PostgreSQL": ("postgresql", "postgres"),
        "Docker": ("docker", "докер"),
        "Telegram bots": ("telegram bot", "telegram-бот", "телеграм-бот", "ботов"),
        "UI/UX": ("ui/ux", "ux/ui", "интерфейс"),
        "Figma": ("figma", "фигма"),
        "Web design": ("web design", "веб-дизайн"),
        "Branding": ("branding", "брендинг", "айдентик"),
        "SMM": ("smm", "смм"),
        "SEO": ("seo", "сео"),
        "Copywriting": ("copywriting", "копирайт", "тексты"),
        "Video editing": ("video editing", "монтаж", "видеомонтаж"),
        "Motion design": ("motion design", "моушн"),
        "AI Agents": ("ai agent", "ии-агент", "ai-агент"),
        "LLM API": ("llm", "gpt", "deepseek"),
        "n8n": ("n8n",),
        "Make": ("make.com",),
        "API integrations": ("api", "интеграц"),
    }
    skills = [name for name, aliases in vocabulary.items() if any(alias in normalized for alias in aliases)]
    specialties = []
    groups = (
        ("Разработка", ("разработ", "frontend", "backend", "сайт", "приложен", "python")),
        ("AI и автоматизация", ("автоматизац", "ai", "ии ", "llm", "n8n")),
        ("Дизайн", ("дизайн", "ui", "ux", "figma", "айдентик")),
        ("Маркетинг", ("маркет", "smm", "seo", "реклам")),
        ("Видео", ("видео", "монтаж", "motion", "моушн")),
        ("Тексты", ("копирай", "редактор", "тексты", "стать")),
    )
    for name, aliases in groups:
        if any(alias in normalized for alias in aliases):
            specialties.append(name)
    rub_values = [
        int(value.replace(" ", ""))
        for value in re.findall(r"(\d[\d ]{2,8})\s*(?:₽|руб|rub)", normalized)
    ]
    return ProfileIntake(
        skills=skills,
        specialties=specialties[:3],
        minimum_project_rub=rub_values[0] if rub_values else None,
    )
