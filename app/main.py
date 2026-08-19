from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.models import entities  # noqa: F401
from app.services.sync import sync_pending_tickets

settings = get_settings()


async def sync_loop():
    while True:
        try:
            await sync_pending_tickets()
        except Exception:
            # Em produção, conectar logging/monitoramento.
            pass
        await asyncio.sleep(max(settings.sync_interval_seconds, 60))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)

    task = None
    if settings.sync_mode.lower() == "loop":
        task = asyncio.create_task(sync_loop())

    yield

    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "AQ Backend",
        "environment": settings.environment,
        "sports_api_configured": bool(settings.sports_api_key),
        "ai_api_configured": bool(settings.openai_api_key),
        "sync_mode": settings.sync_mode,
    }
