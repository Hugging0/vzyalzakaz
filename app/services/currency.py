from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Protocol
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FxRateQuote:
    currency: str
    rate_to_rub: float
    effective_date: date
    source: str


class FxRateProvider(Protocol):
    name: str

    async def get_rate(self, currency: str, on_date: date | None = None) -> FxRateQuote | None: ...


class DisabledFxRateProvider:
    name = "disabled"

    async def get_rate(self, currency: str, on_date: date | None = None) -> FxRateQuote | None:
        return None


class CbrFxRateProvider:
    """Daily official rates from the Bank of Russia XML endpoint.

    One response contains all daily rates, so the cache is shared by currency and
    keyed by the requested date. A failed upstream call never fabricates a rate.
    """

    name = "cbr"

    def __init__(
        self,
        *,
        timeout_seconds: float = 5,
        base_url: str = "https://www.cbr.ru",
        failure_ttl_seconds: float = 300,
    ):
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")
        self.failure_ttl_seconds = failure_ttl_seconds
        self._cache: dict[date | None, dict[str, FxRateQuote]] = {}
        self._failure_until: dict[date | None, float] = {}

    async def get_rate(self, currency: str, on_date: date | None = None) -> FxRateQuote | None:
        code = normalize_currency(currency)
        if code == "RUB":
            effective = on_date or datetime.now(UTC).date()
            return FxRateQuote("RUB", 1.0, effective, self.name)
        if not code:
            return None
        if on_date in self._cache:
            return self._cache[on_date].get(code)
        if self._failure_until.get(on_date, 0) > monotonic():
            return None
        rates = await self._fetch(on_date)
        if rates:
            self._cache[on_date] = rates
            self._failure_until.pop(on_date, None)
            return rates.get(code)
        self._failure_until[on_date] = monotonic() + self.failure_ttl_seconds
        return None

    async def _fetch(self, on_date: date | None) -> dict[str, FxRateQuote]:
        params = {"date_req": on_date.strftime("%d/%m/%Y")} if on_date else None
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = await client.get(f"{self.base_url}/scripts/XML_daily.asp", params=params)
                response.raise_for_status()
            return parse_cbr_rates(response.content)
        except (httpx.HTTPError, ElementTree.ParseError, ValueError):
            logger.warning("fx_rate_fetch_failed provider=cbr requested_date=%s", on_date, exc_info=True)
            return {}


def parse_cbr_rates(payload: bytes | str) -> dict[str, FxRateQuote]:
    root = ElementTree.fromstring(payload)
    raw_date = root.attrib.get("Date")
    if not raw_date:
        raise ValueError("CBR response has no effective date")
    effective = datetime.strptime(raw_date, "%d.%m.%Y").date()
    result: dict[str, FxRateQuote] = {
        "RUB": FxRateQuote("RUB", 1.0, effective, "cbr"),
    }
    for node in root.findall("Valute"):
        code = (node.findtext("CharCode") or "").strip().upper()
        nominal = _decimal(node.findtext("Nominal"))
        value = _decimal(node.findtext("Value"))
        if code and nominal and value is not None and nominal > 0 and value > 0:
            result[code] = FxRateQuote(code, float(value / nominal), effective, "cbr")
    return result


def normalize_currency(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().upper()
    aliases = {
        "₽": "RUB",
        "РУБ": "RUB",
        "РУБ.": "RUB",
        "RUR": "RUB",
        "$": "USD",
        "US$": "USD",
        "€": "EUR",
    }
    return aliases.get(normalized, normalized if len(normalized) == 3 else None)


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value.replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None


def build_fx_provider(provider: str, timeout_seconds: float) -> FxRateProvider:
    if provider == "cbr":
        return CbrFxRateProvider(timeout_seconds=timeout_seconds)
    return DisabledFxRateProvider()
