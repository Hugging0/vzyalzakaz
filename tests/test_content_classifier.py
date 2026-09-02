from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.models import ClassificationMethod, ContentCategory
from app.schemas import RawOpportunity
from app.services.content_classifier import (
    ContentClassifier,
    DeterministicAssessment,
    DeterministicContentClassifier,
    SemanticIntentResult,
    is_demand_category,
)


def raw(text: str, *, policy: str = "mixed") -> RawOpportunity:
    return RawOpportunity(
        source="corpus",
        source_type="telegram",
        external_id=text[:40],
        title=text.splitlines()[0][:120],
        raw_text=text,
        metadata={"source_content_policy": policy},
    )


ENGLISH_DEMAND_CASES = [
    "Looking for a Python developer",
    "We are looking for freelance designers",
    "Hiring React engineer. Remote. $5k/month.",
    "Need video editor ASAP, paid",
    "React dev needed asap",
    "Need SMM specialist for our Telegram channel",
    "DevOps needed, 10h/week",
    "Anyone know a good Python dev? Paid contract.",
    "Looking to hire a contractor for a three-month migration",
    "We need an experienced backend engineer",
    "Seeking a freelance copywriter for our launch",
    "Freelancer needed for a Shopify redesign",
    "Can someone build a Telegram bot for customer support?",
    "Who can help us automate these weekly reports?",
    "Need help with a FastAPI integration",
    "Looking for someone who knows React and Next.js",
    "Our agency is looking for a React developer",
    "Our company is hiring a product designer",
    "Opening for a remote data engineer",
    "Paid task: fix a Python parser today",
    "Please send your CV. We are hiring a Python engineer.",
    "Portfolio required. Looking for a designer.",
    "Looking for 3+ years experience. We need a backend engineer.",
]

ENGLISH_SUPPLY_CASES = [
    ("Python developer looking for work", ContentCategory.JOB_SEEKER),
    ("Freelance designer looking for clients", ContentCategory.SERVICE_OFFER),
    ("React engineer | 6 YOE | Remote | Open to work", ContentCategory.JOB_SEEKER),
    ("Video editor available for paid gigs", ContentCategory.JOB_SEEKER),
    ("SMM specialist looking for Telegram projects", ContentCategory.JOB_SEEKER),
    ("Python dev, open for projects", ContentCategory.JOB_SEEKER),
    ("Available for editing gigs", ContentCategory.JOB_SEEKER),
    ("I am a backend developer looking for a contract", ContentCategory.JOB_SEEKER),
    ("Currently seeking a new role in product design", ContentCategory.JOB_SEEKER),
    ("Looking for freelance work in automation", ContentCategory.JOB_SEEKER),
    ("Open to new opportunities. Python, FastAPI, Docker.", ContentCategory.JOB_SEEKER),
    ("Available immediately for contract work", ContentCategory.JOB_SEEKER),
    ("My experience: 6 years. My stack: React and Node.", ContentCategory.RESUME),
    ("My portfolio, GitHub and LinkedIn. 5 years experience.", ContentCategory.RESUME),
    ("I am a designer. My portfolio and Behance are below.", ContentCategory.RESUME),
    ("We provide software development services", ContentCategory.SERVICE_OFFER),
    ("Our services include marketing and design", ContentCategory.SERVICE_OFFER),
    ("Taking on new clients. DM me for work.", ContentCategory.SERVICE_OFFER),
    ("Available for commissions, hire me", ContentCategory.SERVICE_OFFER),
    ("Book a consultation and get a quote", ContentCategory.SERVICE_OFFER),
    ("Our React agency is looking for clients", ContentCategory.SERVICE_OFFER),
    ("We are a team of developers looking for clients", ContentCategory.AGENCY_OFFER),
    ("Our agency offers marketing services", ContentCategory.AGENCY_OFFER),
]

RUSSIAN_DEMAND_CASES = [
    "Ищу Python-разработчика на проект, бюджет 100 000 ₽",
    "Ищем Python developer на part-time",
    "Нужен монтажёр для Reels, бюджет 15к",
    "Срочно нужен SMM специалист",
    "Требуется React-разработчик на удалёнку",
    "Компания ищет backend инженера",
    "Команда нанимает продуктового дизайнера",
    "Кто сможет сделать Telegram-бота? Задача оплачивается.",
    "Нужно настроить автоматизацию отчётов в n8n",
    "Нужна помощь с интеграцией FastAPI и CRM",
]

RUSSIAN_SUPPLY_CASES = [
    ("Я Python-разработчик, ищу проект", ContentCategory.JOB_SEEKER),
    ("Ищу работу Python backend", ContentCategory.JOB_SEEKER),
    ("В поиске удалённой работы, React разработчик", ContentCategory.JOB_SEEKER),
    ("Открыт к новым проектам, занимаюсь SMM", ContentCategory.JOB_SEEKER),
    ("Ищу клиентов на SMM", ContentCategory.SERVICE_OFFER),
    ("Делаю сайты недорого и под ключ", ContentCategory.SERVICE_OFFER),
    ("Предлагаю услуги видеомонтажа", ContentCategory.SERVICE_OFFER),
    ("Оказываем услуги разработки для бизнеса", ContentCategory.SERVICE_OFFER),
    ("Мой опыт — 7 лет. Мой стек Python и FastAPI.", ContentCategory.RESUME),
    ("Моё портфолио, резюме и опыт работы", ContentCategory.RESUME),
]

MIXED_CASES = [
    ("Ищем Python developer на part-time", True),
    ("Need монтажёр for Reels", True),
    ("Open to work, Python разработчик", False),
    ("Ищу freelance projects, React/Next.js", False),
    ("Нужен React developer ASAP", True),
    ("SMM специалист available for projects", False),
]

OTHER_CASES = [
    ("Check out my portfolio and latest case study", ContentCategory.SELF_PROMOTION),
    ("Подписывайтесь на мой канал — новый кейс уже там", ContentCategory.SELF_PROMOTION),
    ("Enroll now in our Python bootcamp", ContentCategory.COURSE_OR_EDUCATION),
    ("Регистрация на курс по SMM уже открыта", ContentCategory.COURSE_OR_EDUCATION),
    ("Limited time offer: design software is 50% off", ContentCategory.ADVERTISEMENT),
    ("Промокод на сервис, скидка до конца недели", ContentCategory.ADVERTISEMENT),
    ("Register for our AI conference", ContentCategory.EVENT),
    ("Регистрация на хакатон начинается сегодня", ContentCategory.EVENT),
    ("New article: how FastAPI handles dependency injection", ContentCategory.COMMUNITY_POST),
    ("Полезный материал про React, обсудим в комментариях", ContentCategory.COMMUNITY_POST),
    ("Guaranteed income, easy money, no skills required", ContentCategory.SPAM_OR_SCAM),
    ("Гарантированный доход без вложений", ContentCategory.SPAM_OR_SCAM),
]


@pytest.mark.parametrize("text", ENGLISH_DEMAND_CASES)
def test_clear_english_demand_side_is_accepted(text: str) -> None:
    result = DeterministicContentClassifier().classify(raw(text))
    assert is_demand_category(result.category), (text, result)
    assert result.confidence >= 0.86, (text, result)
    assert not result.conflicting_sides


@pytest.mark.parametrize("text,expected", ENGLISH_SUPPLY_CASES)
def test_clear_english_supply_side_is_rejected(text: str, expected: ContentCategory) -> None:
    result = DeterministicContentClassifier().classify(raw(text))
    assert not is_demand_category(result.category), (text, result)
    assert result.category == expected, (text, result)
    assert result.confidence >= 0.82, (text, result)


@pytest.mark.parametrize("text", RUSSIAN_DEMAND_CASES)
def test_clear_russian_demand_side_is_accepted(text: str) -> None:
    result = DeterministicContentClassifier().classify(raw(text))
    assert is_demand_category(result.category), (text, result)
    assert result.confidence >= 0.86, (text, result)


@pytest.mark.parametrize("text,expected", RUSSIAN_SUPPLY_CASES)
def test_clear_russian_supply_side_is_rejected(text: str, expected: ContentCategory) -> None:
    result = DeterministicContentClassifier().classify(raw(text))
    assert result.category == expected, (text, result)
    assert result.confidence >= 0.82, (text, result)


@pytest.mark.parametrize("text,demand_side", MIXED_CASES)
def test_mixed_language_direction(text: str, demand_side: bool) -> None:
    result = DeterministicContentClassifier().classify(raw(text))
    assert is_demand_category(result.category) is demand_side, (text, result)
    assert result.confidence >= 0.82, (text, result)


@pytest.mark.parametrize("text,expected", OTHER_CASES)
def test_non_opportunity_categories(text: str, expected: ContentCategory) -> None:
    result = DeterministicContentClassifier().classify(raw(text))
    assert result.category == expected, (text, result)
    assert result.confidence >= 0.82, (text, result)


@pytest.mark.parametrize(
    "text",
    [
        "Python dev needed, but I am also available if anyone needs help",
        "Looking for React work. Also hiring a designer for our current project.",
        "Need an SMM specialist; alternatively I am open to SMM projects myself",
    ],
)
def test_conflicting_demand_and_supply_requires_fallback(text: str) -> None:
    result = DeterministicContentClassifier().classify(raw(text))
    assert result.conflicting_sides, (text, result)
    assert result.confidence < 0.82


def test_structured_job_feed_hint_is_evidence_not_an_override() -> None:
    job = DeterministicContentClassifier().classify(
        raw("Senior PHP engineer, remote", policy="demand_only")
    )
    candidate = DeterministicContentClassifier().classify(
        raw("Python developer looking for work", policy="demand_only")
    )
    assert job.category == ContentCategory.JOB
    assert job.confidence >= 0.86
    assert candidate.conflicting_sides


@dataclass
class StubSemantic:
    result: SemanticIntentResult | None = None
    error: Exception | None = None
    calls: int = 0

    @property
    def available(self) -> bool:
        return True

    async def classify(
        self,
        raw: RawOpportunity,
        assessment: DeterministicAssessment,
    ) -> SemanticIntentResult:
        del raw, assessment
        self.calls += 1
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


@pytest.mark.asyncio
async def test_high_confidence_path_does_not_call_semantic(settings) -> None:
    semantic = StubSemantic(
        SemanticIntentResult(
            category=ContentCategory.UNKNOWN,
            demand_side=False,
            confidence=0.5,
            reason="unused",
        )
    )
    result = await ContentClassifier(settings, semantic=semantic).classify(
        raw("Looking for a Python developer")
    )
    assert result.category == ContentCategory.JOB
    assert result.method == ClassificationMethod.DETERMINISTIC
    assert semantic.calls == 0


@pytest.mark.asyncio
async def test_ambiguous_message_uses_structured_semantic_fallback(settings) -> None:
    semantic = StubSemantic(
        SemanticIntentResult(
            category=ContentCategory.JOB,
            demand_side=True,
            confidence=0.91,
            reason="The company is the subject of the hiring request",
        )
    )
    result = await ContentClassifier(settings, semantic=semantic).classify(
        raw("A Python collaboration might be possible; details are unclear.")
    )
    assert result.demand_side
    assert result.method == ClassificationMethod.SEMANTIC
    assert result.fallback_used
    assert semantic.calls == 1


@pytest.mark.asyncio
async def test_semantic_failure_is_fail_closed(settings) -> None:
    semantic = StubSemantic(error=TimeoutError())
    result = await ContentClassifier(settings, semantic=semantic).classify(
        raw("Python FastAPI React automation")
    )
    assert result.category == ContentCategory.UNKNOWN
    assert not result.demand_side
    assert result.fallback_used
    assert result.fallback_failed


@pytest.mark.asyncio
async def test_low_confidence_semantic_result_is_fail_closed(settings) -> None:
    semantic = StubSemantic(
        SemanticIntentResult(
            category=ContentCategory.PROJECT,
            demand_side=True,
            confidence=0.65,
            reason="Direction is unclear",
        )
    )
    result = await ContentClassifier(settings, semantic=semantic).classify(
        raw("React project, details in DM")
    )
    assert result.category == ContentCategory.UNKNOWN
    assert not result.demand_side
    assert result.fallback_used
