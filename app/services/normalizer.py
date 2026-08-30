from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass

from app.schemas import RawOpportunity

URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
EXPLICIT_CONTACT_RE = re.compile(
    r"(?:contact|write|message|dm|apply|писать|пишите|связь|контакт|отклик|резюме)"
    r"[^@]{0,50}@([A-Za-z][A-Za-z0-9_]{4,31})",
    re.IGNORECASE,
)
SPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^\w\s+#.-]", re.UNICODE)


@dataclass(slots=True)
class NormalizedContent:
    text: str
    content_hash: str
    contact_username: str | None
    contact_email: str | None


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = unicodedata.normalize("NFKC", value).lower()
    value = URL_RE.sub(" ", value)
    value = PUNCT_RE.sub(" ", value)
    return SPACE_RE.sub(" ", value).strip()


def normalize(raw: RawOpportunity) -> NormalizedContent:
    combined = raw.raw_text or f"{raw.title}\n{raw.description}"
    normalized = normalize_text(combined)
    email_match = EMAIL_RE.search(combined)
    explicit_username = EXPLICIT_CONTACT_RE.search(combined)
    username = raw.contact_username or (f"@{explicit_username.group(1)}" if explicit_username else None)
    email = raw.contact_email or (email_match.group(0) if email_match else None)
    return NormalizedContent(
        text=normalized,
        content_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        contact_username=username,
        contact_email=email,
    )
