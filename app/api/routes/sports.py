from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import current_user
from app.schemas.sports import FixtureAnalysisOut, FixtureOut, TeamFormOut
from app.services.sports import SportsApiError, SportsService

router = APIRouter(prefix="/sports", tags=["sports"], dependencies=[Depends(current_user)])


@router.get("/fixtures/today", response_model=list[FixtureOut])
async def today():
    try:
        return await SportsService().fixtures_by_date(date.today())
    except SportsApiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/fixtures/today/analysis", response_model=list[FixtureAnalysisOut])
async def today_analysis(limit: int = Query(default=12, ge=1, le=20)):
    try:
        return await SportsService().analyzed_fixtures_by_date(date.today(), limit)
    except SportsApiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/fixtures/{target_date}", response_model=list[FixtureOut])
async def by_date(target_date: date):
    try:
        return await SportsService().fixtures_by_date(target_date)
    except SportsApiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/fixtures/{target_date}/analysis", response_model=list[FixtureAnalysisOut])
async def by_date_analysis(target_date: date, limit: int = Query(default=12, ge=1, le=20)):
    try:
        return await SportsService().analyzed_fixtures_by_date(target_date, limit)
    except SportsApiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/teams/{team_id}/last-five", response_model=TeamFormOut)
async def last_five(team_id: int, team_name: str = ""):
    try:
        return await SportsService().recent_team_profile(team_id, team_name)
    except SportsApiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
