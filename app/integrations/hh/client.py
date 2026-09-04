from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import httpx

from app.config import AppSettings
from app.integrations.hh.errors import ERROR_MESSAGES, HHError, error_from_response


class HHClient:
    """Small official-API client. Mutations are never retried automatically."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = settings
        self.transport = transport

    async def search_vacancies(self, params: Mapping[str, Any]) -> dict:
        return await self._request("GET", "/vacancies", params=dict(params), retry_safe=True)

    async def vacancy(self, vacancy_id: str, access_token: str | None = None) -> dict:
        return await self._request(
            "GET", f"/vacancies/{vacancy_id}", access_token=access_token, retry_safe=True
        )

    async def me(self, access_token: str) -> dict:
        return await self._request("GET", "/me", access_token=access_token, retry_safe=True)

    async def resumes(self, access_token: str) -> dict:
        return await self._request("GET", "/resumes/mine", access_token=access_token, retry_safe=True)

    async def suitable_resumes(self, vacancy_id: str, access_token: str) -> dict:
        return await self._request(
            "GET",
            f"/vacancies/{vacancy_id}/suitable_resumes",
            access_token=access_token,
            retry_safe=True,
        )

    async def apply(
        self,
        vacancy_id: str,
        resume_id: str,
        message: str,
        access_token: str,
    ) -> dict:
        return await self._request(
            "POST",
            "/negotiations",
            access_token=access_token,
            data={"vacancy_id": vacancy_id, "resume_id": resume_id, "message": message},
            expected={201},
            retry_safe=False,
            mutation_uncertain=True,
        )

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "client_id": self.settings.hh_client_id,
                "client_secret": self.settings.hh_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            }
        )

    async def refresh_token(self, refresh_token: str) -> dict:
        return await self._token_request(
            {
                "grant_type": "refresh_token",
                "client_id": self.settings.hh_client_id,
                "client_secret": self.settings.hh_client_secret,
                "refresh_token": refresh_token,
            }
        )

    async def _token_request(self, data: dict[str, Any]) -> dict:
        return await self._request("POST", "/token", data=data, expected={200}, retry_safe=False)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        access_token: str | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        expected: set[int] | None = None,
        retry_safe: bool,
        mutation_uncertain: bool = False,
    ) -> dict:
        expected = expected or {200}
        headers = {"HH-User-Agent": self.settings.hh_user_agent, "Accept": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        timeout = httpx.Timeout(self.settings.hh_request_timeout_seconds, connect=5)
        attempts = 3 if retry_safe else 1
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(
                    base_url=self.settings.hh_api_base_url.rstrip("/"),
                    headers=headers,
                    timeout=timeout,
                    transport=self.transport,
                ) as client:
                    response = await client.request(method, path, params=params, data=data)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt + 1 < attempts:
                    await asyncio.sleep(2**attempt)
                    continue
                code = "uncertain" if mutation_uncertain else "temporarily_unavailable"
                raise HHError(code, ERROR_MESSAGES[code], 503, retry_safe) from exc
            if response.status_code in expected:
                if not response.content:
                    return {}
                try:
                    return response.json()
                except ValueError:
                    return {}
            error = error_from_response(response)
            if mutation_uncertain and response.status_code >= 500:
                raise HHError("uncertain", ERROR_MESSAGES["uncertain"], response.status_code)
            if error.retryable and attempt + 1 < attempts:
                try:
                    delay = float(response.headers.get("Retry-After", 2**attempt))
                except ValueError:
                    delay = float(2**attempt)
                delay = min(max(delay, 0), 10)
                await asyncio.sleep(delay)
                continue
            raise error
        raise AssertionError("unreachable")
