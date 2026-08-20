from fastapi import APIRouter, Header

from app.core.security import require_cron_token
from app.services.performance import sync_recommendations
from app.services.sync import sync_pending_tickets

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/sync")
async def sync_all(x_cron_token: str = Header(default="")):
    require_cron_token(x_cron_token)
    tickets = await sync_pending_tickets()
    recommendations = await sync_recommendations(200)
    return {"tickets": tickets, "recommendations": recommendations}
