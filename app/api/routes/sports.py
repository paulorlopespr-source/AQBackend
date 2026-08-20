from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import current_user
from app.schemas.sports import FixtureAnalysisOut, FixtureOut, TeamFormOut
from app.services.advanced_match import AdvancedMatchService
from app.services.calibration import recalibrate_probability
from app.services.opportunity_engine import league_profile
from app.services.sports import SportsApiError, SportsService

router=APIRouter(prefix="/sports",tags=["sports"],dependencies=[Depends(current_user)])


def _classification(probability:int)->str:
    if probability>=80:return "FORTE"
    if probability>=70:return "CONSISTENTE"
    if probability>=60:return "CAUTELA"
    return "EVITAR"


def _league_adjustment(league:str,market:str,selection:str)->float:
    profile=league_profile(league);text=f"{market} {selection}".lower()
    if "gol" in text:
        factor=profile["goal"]
        # Em linhas Under, ambiente menos goleador favorece discretamente a probabilidade; em Over ocorre o inverso.
        return (2.0-factor) if "under" in text else factor
    if "escante" in text or "corner" in text:
        factor=profile["corner"]
        return (2.0-factor) if "under" in text else factor
    return 1.0


def _apply_calibration(rows:list[dict])->list[dict]:
    for row in rows:
        league=str(row.get("league") or "")
        profile=league_profile(league)
        row["league_profile"]={"goal_factor":profile["goal"],"corner_factor":profile["corner"],"confidence_factor":profile["confidence"]}
        for signal in row.get("market_probabilities",[]):
            raw=int(signal.get("probability") or 0)
            adjusted,weight=recalibrate_probability(raw)
            league_factor=_league_adjustment(league,str(signal.get("market") or ""),str(signal.get("selection") or ""))
            # O perfil da liga é deliberadamente limitado a ±6% relativo para não dominar os dados recentes.
            league_factor=max(.94,min(1.06,league_factor))
            adjusted=round(adjusted*league_factor);adjusted=max(1,min(99,adjusted))
            signal["probability"]=adjusted
            signal["fair_odd"]=round(100/max(adjusted,1),2)
            confidence=round(int(signal.get("data_confidence") or 0)*profile["confidence"]);confidence=max(0,min(100,confidence));signal["data_confidence"]=confidence
            if confidence<60:signal["risk"]="ALTO"
            elif adjusted>=80 and confidence>=80:signal["risk"]="BAIXO"
            elif adjusted>=68:signal["risk"]="MODERADO"
            else:signal["risk"]="ALTO"
            notes=[]
            if weight!=1.0:notes.append(f"recalibração histórica {weight:.3f}x")
            if abs(league_factor-1.0)>.001:notes.append(f"perfil {league} {league_factor:.3f}x")
            if notes:signal["rationale"]=f"{signal.get('rationale','')} Ajustes AQ: {', '.join(notes)}.".strip()
    return rows


def _calibrate_decision_card(card:dict)->dict:
    confidence=int(card.get("data_confidence") or 0)
    for signal in card.get("signals",[]):
        raw=int(signal.get("probability") or 0);adjusted,weight=recalibrate_probability(raw);signal["probability"]=adjusted;signal["classification"]=_classification(adjusted)
        signal_confidence=int(signal.get("confidence") or confidence)
        if signal_confidence<60:signal["risk"]="ALTO"
        elif adjusted>=80 and signal_confidence>=80:signal["risk"]="BAIXO"
        elif adjusted>=68:signal["risk"]="MODERADO"
        else:signal["risk"]="ALTO"
        if weight!=1.0:signal["reason"]=f"{signal.get('reason','')} Recalibração histórica AQ aplicada ({weight:.3f}x).".strip()
    signals=card.get("signals",[]);signals.sort(key=lambda item:int(item.get("probability") or 0),reverse=True)
    top=next((s for s in signals if s.get("classification") in {"FORTE","CONSISTENTE"} and int(s.get("confidence") or 0)>=60),None)
    if top:card["prelive_strategy"]=f"{top['market']} • {top['selection']} — {top['probability']}% ({str(top['classification']).lower()})."
    return card


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
    try:return _calibrate_decision_card(await AdvancedMatchService().decision_card(fixture_id,force_refresh=refresh))
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
