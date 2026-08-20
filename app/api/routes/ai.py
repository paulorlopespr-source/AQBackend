from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import current_user
from app.services.ai import AiService
from app.services.performance import log_recommendations

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(current_user)])


class MatchAiRequest(BaseModel):
    fixture_id: int | str
    league: str
    home_team: str
    away_team: str
    kickoff: str = ""
    aq_score: int = 0
    data_confidence: int = 0
    expected_goals_home: float = 0
    expected_goals_away: float = 0
    expected_corners: float = 0
    expected_shots: float = 0
    expected_shots_on_target: float = 0
    home_form: dict[str, Any] = Field(default_factory=dict)
    away_form: dict[str, Any] = Field(default_factory=dict)
    market_probabilities: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


@router.get("/status")
def ai_status():
    service = AiService()
    return {"configured": service.configured,"policy": "IA interpreta resultados quantitativos; não inventa a probabilidade-base."}


@router.post("/match-analysis")
async def match_analysis(request: MatchAiRequest):
    payload=request.model_dump()
    analysis=await AiService().analyze_match(payload)
    try:
        analysis["tracked_recommendations"]=log_recommendations(payload,analysis)
    except Exception:
        analysis["tracked_recommendations"]=0
    return analysis
