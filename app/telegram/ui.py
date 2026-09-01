from __future__ import annotations

from typing import Literal

ButtonStyle = Literal["primary", "success", "danger"]


def button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    web_app_url: str | None = None,
    style: ButtonStyle | None = None,
) -> dict:
    """Build one Bot API button and keep the visual contract in one place."""
    actions = [callback_data is not None, url is not None, web_app_url is not None]
    if sum(actions) != 1:
        raise ValueError("A Telegram button must have exactly one action")
    result = {"text": text}
    if callback_data is not None:
        result["callback_data"] = callback_data
    elif url is not None:
        result["url"] = url
    else:
        result["web_app"] = {"url": web_app_url}
    if style:
        result["style"] = style
    return result


def app_button(text: str, url: str, *, style: ButtonStyle = "primary") -> dict:
    return button(text, web_app_url=url, style=style)
