from fastapi import APIRouter, Depends, Query

from app.core.security import current_user
from app.services.performance import bankroll_execution_report, calibration_weights, recommendation_report, sync_recommendations

router = APIRouter(prefix="/performance", tags=["performance"], dependencies=[Depends(current_user)])

@router.get("/recommendations")
def recommendations():
    return recommendation_report()

@router.get("/execution")
def execution():
    return bankroll_execution_report()

@router.get("/calibration")
def calibration():
    return calibration_weights()

@router.post("/recommendations/sync")
async def sync(limit: int = Query(default=100, ge=1, le=500)):
    return await sync_recommendations(limit)
