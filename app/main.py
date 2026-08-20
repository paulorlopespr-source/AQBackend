from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.models import entities  # noqa: F401
from app.services.performance import sync_recommendations
from app.services.sync import sync_pending_tickets

settings=get_settings()
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger=logging.getLogger("aq")


def apply_safe_schema_updates() -> None:
    """Small additive updates for existing production databases.

    `create_all` creates new tables but does not add columns to existing tables.
    This migration is intentionally additive and idempotent.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "aq_recommendations" in tables:
        columns = {c["name"] for c in inspector.get_columns("aq_recommendations")}
        if "model_version" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE aq_recommendations ADD COLUMN model_version VARCHAR(30) DEFAULT 'AQ Model 1.0'"))


async def sync_loop():
    while True:
        try:
            ticket_result=await sync_pending_tickets()
            recommendation_result=await sync_recommendations(200)
            logger.info("sync tickets=%s recommendations=%s",ticket_result,recommendation_result)
        except Exception:
            logger.exception("background sync failed")
        await asyncio.sleep(max(settings.sync_interval_seconds,60))


@asynccontextmanager
async def lifespan(app:FastAPI):
    Base.metadata.create_all(bind=engine)
    apply_safe_schema_updates()
    task=None
    if settings.sync_mode.lower()=="loop":task=asyncio.create_task(sync_loop())
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):await task


app=FastAPI(title=settings.app_name,version="0.3.0-beta",lifespan=lifespan)

if settings.cors_origin_list:
    app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origin_list,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status":"ok","service":"AQ Backend","version":"0.3.0-beta","environment":settings.environment,"sports_api_configured":bool(settings.sports_api_key),"ai_api_configured":bool(settings.openai_api_key),"sync_mode":settings.sync_mode}


@app.get("/ready")
def ready():
    with engine.connect() as conn:conn.execute(text("SELECT 1"))
    return {"status":"ready","database":"connected","sports_api_configured":bool(settings.sports_api_key),"ai_api_configured":bool(settings.openai_api_key)}
