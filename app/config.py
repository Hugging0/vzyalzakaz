from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Candidate(BaseModel):
    name: str = "Candidate"
    languages: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    secondary_skills: list[str] = Field(default_factory=list)
    about: str = ""


class Availability(BaseModel):
    max_hours_week: int = 15
    weekdays_hours: int = 2
    weekend_hours: int = 5


class Preferences(BaseModel):
    remote: bool = True
    freelance: bool = True
    project: bool = True
    fixed_price: bool = True
    contract: bool = True
    part_time: bool = True
    asynchronous: bool = True


class Avoid(BaseModel):
    full_time: bool = True
    office: bool = True
    relocation: bool = True
    daily_daytime_calls: bool = True
    coursework: bool = True


class Economics(BaseModel):
    minimum_project_rub: int = 10_000
    target_hourly_rub: int = 2_000


class Ranking(BaseModel):
    fit_weight: float = 0.40
    money_weight: float = 0.25
    win_weight: float = 0.25
    freshness_weight: float = 0.10
    realtime_threshold: float = 82
    digest_threshold: float = 70


class CandidateProfile(BaseModel):
    candidate: Candidate
    availability: Availability = Field(default_factory=Availability)
    preferred: Preferences = Field(default_factory=Preferences)
    avoid: Avoid = Field(default_factory=Avoid)
    economics: Economics = Field(default_factory=Economics)
    ranking: Ranking = Field(default_factory=Ranking)


class SourceConfig(BaseModel):
    name: str
    type: Literal["telegram", "web", "rss", "api"]
    language: str = "en"
    priority: Literal["tier_a", "tier_b", "tier_c"] = "tier_b"
    enabled: bool = True
    collector: str
    apply_mode: Literal["send_allowed", "draft_only", "api_allowed"] = "draft_only"
    poll_interval: int = 1800
    url: str | None = None
    channel: str | None = None
    options: dict = Field(default_factory=dict)


class PortfolioProject(BaseModel):
    slug: str
    title: str
    description: str
    skills: list[str] = Field(default_factory=list)
    url: str | None = None


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/jobhunter.db"
    config_dir: Path = Path("config")
    log_level: str = "INFO"
    enable_scheduler: bool = True
    enable_telegram_collector: bool = True
    enable_telegram_bot: bool = True

    llm_provider: Literal["deepseek", "openrouter", "disabled"] = "disabled"
    llm_api_key: str | None = None
    llm_model: str = "deepseek-chat"
    llm_base_url: str | None = None
    llm_timeout_seconds: int = 45

    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_phone: str | None = None
    telegram_session_path: str = "./data/jobhunter"
    telegram_bot_token: str | None = None
    telegram_owner_id: int | None = None
    mini_app_url: str | None = None
    registration_mode: Literal["open", "invite", "closed"] = "open"
    registration_invite_code: str | None = None
    max_users: int = 100
    onboarding_backfill_limit: int = 200
    mini_app_session_secret: str | None = None
    mini_app_auth_max_age_seconds: int = 86_400
    mini_app_session_ttl_seconds: int = 604_800
    allow_dev_auth: bool = False
    dev_telegram_user_id: int | None = None

    public_base_url: str | None = None
    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None
    billing_pro_monthly_price_rub: Decimal = Decimal("990.00")

    @field_validator("telegram_api_id", "telegram_owner_id", "dev_telegram_user_id", mode="before")
    @classmethod
    def empty_optional_integer(cls, value):
        return None if value == "" else value

    @property
    def telegram_user_ready(self) -> bool:
        return bool(self.telegram_api_id and self.telegram_api_hash)

    @property
    def telegram_bot_ready(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def yookassa_ready(self) -> bool:
        return bool(self.yookassa_shop_id and self.yookassa_secret_key and self.public_base_url)

    def load_profile(self) -> CandidateProfile:
        return CandidateProfile.model_validate(_read_yaml(self.config_dir / "candidate_profile.yaml"))

    def load_sources(self) -> list[SourceConfig]:
        data = _read_yaml(self.config_dir / "sources.yaml")
        return [SourceConfig.model_validate(item) for item in data.get("sources", [])]

    def load_portfolio(self) -> list[PortfolioProject]:
        data = _read_yaml(self.config_dir / "portfolio.yaml")
        return [PortfolioProject.model_validate(item) for item in data.get("projects", [])]


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"Configuration file not found: {path}")
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
