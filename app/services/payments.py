from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings
from app.models import Payment, PaymentStatus, TelegramUser

YOOKASSA_PAYMENTS_URL = "https://api.yookassa.ru/v3/payments"
PRO_MONTHLY = "pro_monthly"


class YooKassaService:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    def _auth(self) -> httpx.BasicAuth:
        if not self.settings.yookassa_ready:
            raise HTTPException(503, "Оплата временно недоступна")
        return httpx.BasicAuth(self.settings.yookassa_shop_id, self.settings.yookassa_secret_key)

    async def create_payment(
        self, session: AsyncSession, user: TelegramUser, idempotency_key: str
    ) -> Payment:
        existing = await session.scalar(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        if existing:
            if existing.user_id != user.id:
                raise HTTPException(409, "Idempotency key belongs to another user")
            return existing
        amount = self.settings.billing_pro_monthly_price_rub.quantize(Decimal("0.01"))
        return_url = f"{self.settings.public_base_url.rstrip('/')}/app?payment=return"
        payload = {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": "Hunt Agent Pro — 30 дней",
            "metadata": {"telegram_user_id": str(user.telegram_user_id), "plan": PRO_MONTHLY},
        }
        try:
            async with httpx.AsyncClient(timeout=20, auth=self._auth()) as client:
                response = await client.post(
                    YOOKASSA_PAYMENTS_URL,
                    headers={"Idempotence-Key": idempotency_key},
                    json=payload,
                )
                response.raise_for_status()
                provider_payment = response.json()
        except httpx.HTTPError as exc:
            raise HTTPException(502, "Не удалось создать платёж в ЮKassa") from exc
        payment = Payment(
            user_id=user.id,
            idempotency_key=idempotency_key,
            provider_payment_id=provider_payment["id"],
            plan_code=PRO_MONTHLY,
            amount_rub=f"{amount:.2f}",
            status=_status(provider_payment.get("status")),
            confirmation_url=(provider_payment.get("confirmation") or {}).get("confirmation_url"),
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        return payment

    async def refresh_payment(self, session: AsyncSession, payment: Payment) -> Payment:
        if not payment.provider_payment_id:
            return payment
        try:
            async with httpx.AsyncClient(timeout=20, auth=self._auth()) as client:
                response = await client.get(f"{YOOKASSA_PAYMENTS_URL}/{payment.provider_payment_id}")
                response.raise_for_status()
                provider_payment = response.json()
        except httpx.HTTPError as exc:
            raise HTTPException(502, "Не удалось проверить статус платежа") from exc
        payment.status = _status(provider_payment.get("status"))
        if payment.status == PaymentStatus.SUCCEEDED and not payment.paid_at:
            payment.paid_at = datetime.now(UTC)
            user = await session.get(TelegramUser, payment.user_id)
            profile = dict(user.profile or {})
            profile["billing"] = {
                "plan": payment.plan_code,
                "active_until": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            }
            user.profile = profile
        await session.commit()
        await session.refresh(payment)
        return payment


def _status(value: str | None) -> PaymentStatus:
    try:
        return PaymentStatus(value or PaymentStatus.PENDING)
    except ValueError:
        return PaymentStatus.PENDING


def payment_payload(payment: Payment | None) -> dict:
    if not payment:
        return {"available": False, "status": None, "plan": None, "active_until": None}
    return {
        "available": True,
        "status": payment.status.value,
        "plan": payment.plan_code,
        "amount_rub": payment.amount_rub,
        "confirmation_url": payment.confirmation_url,
        "active_until": None,
    }
