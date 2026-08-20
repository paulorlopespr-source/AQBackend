from fastapi import APIRouter

from app.api.routes import ai, auth, bankroll, entries, internal, methods, sports, tickets

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(bankroll.router)
api_router.include_router(methods.router)
api_router.include_router(entries.router)
api_router.include_router(sports.router)
api_router.include_router(tickets.router)
api_router.include_router(ai.router)
api_router.include_router(internal.router)
