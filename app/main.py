from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.config import get_settings
from app.database import SessionLocal, engine
from app.extension_api import router as extension_router
from app.mini_app_api import router as mini_app_router
from app.models import Base
from app.runtime import Runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx may otherwise log the Telegram Bot API URL, which contains the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    runtime = Runtime(settings, SessionLocal)
    app.state.runtime = runtime
    await runtime.start()
    try:
        yield
    finally:
        await runtime.stop()
        await engine.dispose()


app = FastAPI(
    title="Personal AI JobHunter",
    version="0.1.0",
    description="Self-hosted opportunity collection and ranking API",
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(mini_app_router)
app.include_router(extension_router)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {"name": "Personal AI JobHunter", "docs": "/docs", "health": "/api/health"}
