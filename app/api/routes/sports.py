from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import current_user
from app.schemas.sports import FixtureAnalysisOut, FixtureOut, TeamFormOut
from app.services.advanced_match import AdvancedMatchService
from app.services.calibration import recalibrate_probability
from app.services.sports import SportsApiError, SportsService

router=APIRouter(prefix="/sports",tags=["sports"],dependencies=[Depends(current_user)])


def _apply_calibration(rows:list[dict])->list[dict]:
    for row in rows:
        for signal in row.get("market_probabilities",[]):
            raw=int(signal.get("probability") or 0)
            adjusted,weight=recalibrate_probability(raw)
            signal["probability"]=adjusted
            signal["fair_odd"]=round(100/max(adjusted,1),2)
            confidence=int(signal.get("data_confidence") or 0)
            if confidence<60:signal["risk"]="ALTO"
            elif adjusted>=80 and confidence>=80:signal["risk"]="BAIXO"
            elif adjusted>=68:signal["risk"]="MODERADO"
            else:signal["risk"]="ALTO"
            if weight!=1.0:
                signal["rationale"]=f"{signal.get('rationale','')} Recalibração histórica AQ aplicada ({weight:.3f}x).".strip()
    return rows


@router.get("/fixtures/today",response_model=list[FixtureOut])
async def today(refresh:bool=Query(default=False)):
    try:return await SportsService().fixtures_by_date(date.today(),force_refresh=refresh)
    except SportsApiError as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc


@router.get("/fixtures/today/analysis",response_model=list[FixtureAnalysisOut])
async def today_analysis(limit:int=Query(default=12,ge=1,le=20),refresh:bool=Query(default=False)):
    try:return _apply_calibration(await SportsService().analyzed_fixtures_by_date(date.today(),limit,force_refresh=refresh))
    except SportsApiError as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc


@router.get("/live")
async def live_monitor(limit:int=Query(default=12,ge=1,le=20),refresh:bool=Query(default=True)):
    try:return await AdvancedMatchService().live_matches(force_refresh=refresh,limit=limit)
    except SportsApiError as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc


@router.get("/fixture/{fixture_id}/decision-card")
async def decision_card(fixture_id:int,refresh:bool=Query(default=False)):
    try:return await AdvancedMatchService().decision_card(fixture_id,force_refresh=refresh)
    except SportsApiError as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc


@router.get("/cache/status")
async def cache_status():return SportsService.cache_stats()

@router.delete("/cache")
async def clear_cache():return {"cleared":SportsService.clear_cache()}

@router.get("/fixtures/{target_date}",response_model=list[FixtureOut])
async def by_date(target_date:date,refresh:bool=Query(default=False)):
    try:return await SportsService().fixtures_by_date(target_date,force_refresh=refresh)
    except SportsApiError as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc

@router.get("/fixtures/{target_date}/analysis",response_model=list[FixtureAnalysisOut])
async def by_date_analysis(target_date:date,limit:int=Query(default=12,ge=1,le=20),refresh:bool=Query(default=False)):
    try:return _apply_calibration(await SportsService().analyzed_fixtures_by_date(target_date,limit,force_refresh=refresh))
    except SportsApiError as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc

@router.get("/teams/{team_id}/last-five",response_model=TeamFormOut)
async def last_five(team_id:int,team_name:str="",refresh:bool=Query(default=False)):
    try:return await SportsService().recent_team_profile(team_id,team_name,force_refresh=refresh)
    except SportsApiError as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc
