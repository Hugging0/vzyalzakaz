from __future__ import annotations

import asyncio
import getpass

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from app.config import get_settings


async def authorize() -> None:
    settings = get_settings()
    if not settings.telegram_user_ready or not settings.telegram_phone:
        raise SystemExit("Set TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_PHONE in .env first")
    client = TelegramClient(
        settings.telegram_session_path,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
    await client.connect()
    if await client.is_user_authorized():
        print("Telegram session is already authorized.")
        await client.disconnect()
        return
    sent = await client.send_code_request(settings.telegram_phone)
    code = input("Telegram login code: ").strip()
    try:
        await client.sign_in(settings.telegram_phone, code, phone_code_hash=sent.phone_code_hash)
    except SessionPasswordNeededError:
        await client.sign_in(password=getpass.getpass("Telegram 2FA password: "))
    print(f"Authorized. Session saved at {settings.telegram_session_path}.session")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(authorize())
