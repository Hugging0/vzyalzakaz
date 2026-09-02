from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import AppSettings


class ChatCompletionClient:
    """Shared OpenAI-compatible client for narrow backend LLM tasks."""

    def __init__(self, settings: AppSettings):
        self.settings = settings

    @property
    def available(self) -> bool:
        return self.settings.llm_provider != "disabled" and bool(self.settings.llm_api_key)

    async def complete(
        self,
        prompt: str,
        *,
        system: str,
        json_mode: bool = True,
        model: str | None = None,
        max_tokens: int | None = None,
        timeout_seconds: int | None = None,
    ) -> dict | str:
        if not self.available:
            raise RuntimeError("LLM provider is not configured")
        base_url = (
            self.settings.llm_base_url
            or {
                "deepseek": "https://api.deepseek.com",
                "openrouter": "https://openrouter.ai/api/v1",
            }[self.settings.llm_provider]
        )
        payload: dict[str, Any] = {
            "model": model or self.settings.llm_model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        if self.settings.llm_provider == "openrouter":
            headers.update(
                {"HTTP-Referer": "https://vzyalzakaz.ru", "X-Title": "VzyalZakaz"}
            )
        timeout = timeout_seconds or self.settings.llm_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not json_mode:
            return content
        content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
        return json.loads(content)
