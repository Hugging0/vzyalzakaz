from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class HHError(Exception):
    code: str
    user_message: str
    status_code: int = 502
    retryable: bool = False

    def __str__(self) -> str:
        return self.user_message


ERROR_MESSAGES = {
    "already_applied": "Вы уже откликались на эту вакансию.",
    "test_required": "Для отклика нужно пройти тест на HH.",
    "resume_not_found": "Выбранное резюме недоступно для этой вакансии.",
    "resume_visibility_conflict": "Откройте видимость резюме для этого работодателя на HH.",
    "application_denied": "HH не разрешает отклик на эту вакансию через API.",
    "limit_exceeded": "На HH достигнут лимит откликов.",
    "vacancy_not_found": "Вакансия закрыта или больше недоступна.",
    "invalid_vacancy": "На эту вакансию нельзя откликнуться через API.",
    "wrong_state": "Отклик уже находится в другом состоянии.",
    "auth_required": "Подключение HH устарело. Авторизуйтесь снова.",
    "rate_limited": "HH временно ограничил запросы. Повторите позже.",
    "temporarily_unavailable": "HH временно недоступен. Повторите позже.",
    "request_failed": "HH не принял запрос. Проверьте данные и повторите.",
    "uncertain": "HH не подтвердил результат. Проверьте отклики на HH перед повтором.",
}


def error_from_response(response: httpx.Response) -> HHError:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    entries = payload.get("errors") if isinstance(payload, dict) else None
    first = entries[0] if isinstance(entries, list) and entries else {}
    error_type = str(first.get("type") or payload.get("error") or "")
    value = str(first.get("value") or "")
    candidates = (value, error_type)
    code = next((item for item in candidates if item in ERROR_MESSAGES), None)
    if response.status_code in {401, 403} and code is None:
        auth_markers = {"oauth", "forbidden", "invalid_token", "token_expired", "token-revoked"}
        code = (
            "auth_required"
            if response.status_code == 401 or any(item in auth_markers for item in candidates)
            else "application_denied"
        )
    elif response.status_code == 404 and code is None:
        code = "vacancy_not_found"
    elif response.status_code == 429:
        code = "rate_limited"
    elif response.status_code >= 500:
        code = "temporarily_unavailable"
    code = code or "request_failed"
    return HHError(
        code=code,
        user_message=ERROR_MESSAGES[code],
        status_code=response.status_code,
        retryable=response.status_code == 429 or response.status_code >= 500,
    )
