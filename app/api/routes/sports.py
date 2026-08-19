from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import current_user
from app.schemas.sports import FixtureOut, TeamFormOut
from app.services.sports import SportsApiError, SportsService

router = APIRouter(prefix="/sports", tags=["sports"], dependencies=[Depends(current_user)])


@router.get("/fixtures/today", response_model=list[FixtureOut])
async def today():
    try:
        return await SportsService().fixtures_by_date(date.today())
    except SportsApiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/fixtures/{target_date}", response_model=list[FixtureOut])
async def by_date(target_date: date):
    try:
        return await SportsService().fixtures_by_date(target_date)
    except SportsApiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/teams/{team_id}/last-five", response_model=TeamFormOut)
async def last_five(team_id: int, team_name: str = ""):
    try:
        rows = await SportsService().last_five(team_id)
    except SportsApiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    wins = draws = losses = 0
    goals_for = goals_against = 0

    for row in rows:
        home = row["teams"]["home"]["id"] == team_id
        gf = row["goals"]["home"] if home else row["goals"]["away"]
        ga = row["goals"]["away"] if home else row["goals"]["home"]
        if gf is None or ga is None:
            continue
        goals_for += gf
        goals_against += ga
        if gf > ga:
            wins += 1
        elif gf == ga:
            draws += 1
        else:
            losses += 1

    count = wins + draws + losses
    points = wins * 3 + draws
    score = round(points / (count * 3) * 100) if count else 50

    label = "BOA_FASE" if score >= 67 else "ESTAVEL" if score >= 40 else "MA_FASE"

    return TeamFormOut(
        team_id=team_id,
        team=team_name or str(team_id),
        wins=wins,
        draws=draws,
        losses=losses,
        avg_goals_for=goals_for / count if count else 0,
        avg_goals_against=goals_against / count if count else 0,
        form_score=score,
        form_label=label,
    )
