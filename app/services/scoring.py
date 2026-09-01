from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.config import AppSettings, CandidateProfile, PortfolioProject
from app.schemas import LLMAnalysis, ProfileIntake, RawOpportunity
from app.services.normalizer import normalize_text

logger = logging.getLogger(__name__)


class OpportunityAnalyzer:
    def __init__(self, settings: AppSettings, profile: CandidateProfile):
        self.settings = settings
        self.profile = profile

    async def analyze(self, raw: RawOpportunity, portfolio: PortfolioProject | None) -> LLMAnalysis:
        if self.settings.llm_provider == "disabled" or not self.settings.llm_api_key:
            return self._deterministic_analysis(raw, portfolio)
        try:
            result = await self._call_llm(self._analysis_prompt(raw, portfolio))
            return LLMAnalysis.model_validate(result)
        except Exception:
            logger.exception(
                "LLM analysis failed for %s:%s; using local scoring", raw.source, raw.external_id
            )
            return self._deterministic_analysis(raw, portfolio)

    async def generate_proposal(
        self, raw: RawOpportunity, analysis: dict[str, Any], portfolio: PortfolioProject | None
    ) -> str:
        if self.settings.llm_provider == "disabled" or not self.settings.llm_api_key:
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
        base_url = (
            self.settings.llm_base_url
            or {
                "deepseek": "https://api.deepseek.com",
                "openrouter": "https://openrouter.ai/api/v1",
            }[self.settings.llm_provider]
        )
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise job opportunity analyst. Never invent facts.",
                },
                {"role": "user", "content": prompt},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        if self.settings.llm_provider == "openrouter":
            headers.update(
                {"HTTP-Referer": "https://localhost/jobhunter", "X-Title": "Personal AI JobHunter"}
            )
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not json_mode:
            return content
        content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
        return json.loads(content)

    def _analysis_prompt(self, raw: RawOpportunity, portfolio: PortfolioProject | None) -> str:
        profile = self.profile
        schema = json.dumps(LLMAnalysis.model_json_schema(), ensure_ascii=False)
        return f"""
Analyze the opportunity for a person seeking only remote freelance/project/part-time work,
up to {profile.availability.max_hours_week} hours/week, mostly evenings/weekends.
Candidate skills: {", ".join(profile.candidate.skills)}.
Secondary skills: {", ".join(profile.candidate.secondary_skills)}.
Target rate: {profile.economics.target_hourly_rub} RUB/hour.
Portfolio match: {portfolio.model_dump_json() if portfolio else "none"}.

Opportunity title: {raw.title}
Source: {raw.source}
Budget: {raw.budget_min} - {raw.budget_max} {raw.currency}
Text:
{(raw.raw_text or raw.description)[:12000]}

Return only valid JSON matching this schema: {schema}
Scores are ranking heuristics from 0 to 100. Penalize full-time/daytime/office work heavily.
Do not claim WIN is a statistical probability.
""".strip()

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

    def _deterministic_analysis(self, raw: RawOpportunity, portfolio: PortfolioProject | None) -> LLMAnalysis:
        text = normalize_text(f"{raw.title} {raw.description} {raw.raw_text}")
        candidate_skills = self.profile.candidate.skills
        matched = [skill for skill in candidate_skills if normalize_text(skill) in text]
        fit = min(96, 52 + len(matched) * 11 + (8 if portfolio else 0))
        full_time = any(term in text for term in ("full time", "full-time", "полная занятость", "40 hours"))
        office = any(term in text for term in ("office only", "on site", "только офис", "в офисе"))
        if full_time:
            fit -= 45
        if office:
            fit -= 50

        expected = raw.budget_max or raw.budget_min
        hours = raw.estimated_hours or min(40, max(5, self.profile.availability.max_hours_week))
        hourly = expected / hours if expected and raw.currency == "RUB" else None
        target = self.profile.economics.target_hourly_rub
        if hourly is None:
            money = 45
            budget_quality = "unknown"
        elif hourly >= target * 1.25:
            money, budget_quality = 90, "excellent"
        elif hourly >= target * 0.75:
            money, budget_quality = 72, "good"
        elif hourly >= target * 0.5:
            money, budget_quality = 50, "acceptable"
        else:
            money, budget_quality = 20, "low"

        win = min(90, 45 + len(matched) * 9 + (12 if portfolio else 0))
        if full_time:
            win -= 25
        if office:
            win -= 30
        risks = []
        if not expected:
            risks.append("Бюджет не указан")
        if full_time:
            risks.append("Похоже на full-time занятость")
        if office:
            risks.append("Возможна обязательная работа из офиса")
        missing = []
        summary = (raw.description or raw.raw_text or raw.title).strip()[:500]
        return LLMAnalysis(
            job_type=raw.employment_type or "unknown",
            summary=summary,
            required_skills=matched,
            missing_skills=missing,
            budget_quality=budget_quality,
            estimated_hours=hours,
            possible_with_vibe_coding=bool(matched),
            requires_daytime_presence=full_time or office,
            fit_reason=("Совпали навыки: " + ", ".join(matched)) if matched else "Требуется ручная проверка",
            risks=risks,
            recommended_portfolio_project=portfolio.slug if portfolio else "",
            fit_score=max(0, fit),
            money_score=money,
            win_score=max(0, win),
        )

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
