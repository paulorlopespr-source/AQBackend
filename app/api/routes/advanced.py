from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import current_user
from app.db.session import get_db
from app.models.entities import AuditLog, Bankroll, BetEntryHistory, BetTicket, SimulationBet, TicketStatus
from app.services.advanced_match import AdvancedMatchService
from app.services.deep_analysis import DeepAnalysisService
from app.services.opportunity_engine import MODEL_VERSION, correlation_penalty, dynamic_stake, model_metadata, opportunity_score, probability_class
from app.services.performance import recommendation_report
from app.services.settlement import settle_leg
from app.services.sports import SportsApiError, SportsService

router = APIRouter(prefix="/advanced", tags=["advanced"], dependencies=[Depends(current_user)])


class OpportunityFilters(BaseModel):
    league: str = ""
    market: str = ""
    min_probability: int = Field(default=0, ge=0, le=99)
    risk: str = ""
    min_ev: float = -999
    mode: str = ""
    value_only: bool = False
    strong_only: bool = False


class StakeRequest(BaseModel):
    fixture_id: int | None = None
    market: str
    selection: str
    probability: int = Field(ge=1, le=99)
    confidence: int = Field(ge=0, le=100)
    ev_percent: float | None = None
    risk: str = "MODERADO"
    drawdown_percent: float = 0
    red_streak: int = 0


class SimulationCreate(BaseModel):
    fixture_id: int
    match_label: str
    league: str = ""
    market: str
    selection: str
    probability: int = Field(ge=1, le=99)
    confidence: int = Field(ge=0, le=100)
    odd: float = Field(gt=1.0)
    stake_unit: float = Field(default=1.0, gt=0)
    mode: str = "PRE_LIVE"


def audit(db: Session, event_type: str, entity_type: str = "", entity_id: str = "", message: str = "", payload: dict | None = None) -> None:
    db.add(AuditLog(event_type=event_type, entity_type=entity_type, entity_id=entity_id, message=message, payload_json=json.dumps(payload or {}, ensure_ascii=False, default=str)))


def _pending_exposure(db: Session, bankroll: Bankroll) -> tuple[float, float, list[dict[str, Any]]]:
    stmt = select(BetTicket).where(BetTicket.status.in_([TicketStatus.PENDING.value, TicketStatus.WAITING_STATS.value])).options(selectinload(BetTicket.legs))
    tickets = list(db.scalars(stmt).all())
    pending = sum(float(t.stake) for t in tickets)
    pct = pending / max(float(bankroll.current_value) + pending, 1.0) * 100.0
    selections: list[dict[str, Any]] = []
    for ticket in tickets:
        for leg in ticket.legs:
            selections.append({"fixture_id": leg.fixture_id, "market": leg.market_label, "selection": f"{leg.selection_side} {leg.line or ''}"})
    return pending, pct, selections


@router.get("/opportunities")
async def opportunities(
    league: str = "", market: str = "", min_probability: int = Query(default=0, ge=0, le=99), risk: str = "",
    min_ev: float = -999, mode: str = "", value_only: bool = False, strong_only: bool = False,
):
    try:
        rows = await SportsService().analyzed_fixtures_by_date(date.today(), limit=20)
        live_rows = await AdvancedMatchService().live_matches(force_refresh=False, limit=20)
    except SportsApiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    out: list[dict[str, Any]] = []
    for row in rows:
        for signal in row.get("market_probabilities", []):
            item = {
                "fixture_id": row["fixture_id"], "league": row["league"], "kickoff": row["kickoff"],
                "home_team": row["home_team"], "away_team": row["away_team"], "mode": "PRE_LIVE",
                **signal,
            }
            item["classification"] = probability_class(int(item.get("probability") or 0))
            item["opportunity_score"] = opportunity_score(item)
            out.append(item)
    for live in live_rows:
        alert = live.get("alert", {})
        if alert.get("status") != "ENTRADA_DETECTADA":
            continue
        item = {
            "fixture_id": live["fixture_id"], "league": live["league"], "kickoff": "AO VIVO",
            "home_team": live["home_team"], "away_team": live["away_team"], "mode": "LIVE",
            "market": alert.get("market", "Ao Vivo"), "selection": alert.get("market", ""),
            "probability": alert.get("probability", 0), "data_confidence": min(95, 60 + alert.get("pressure_index", 0) // 4),
            "risk": alert.get("risk", "MODERADO"), "rationale": alert.get("message", ""), "fair_odd": 0,
            "best_odd": None, "bookmaker": None, "ev_percent": None, "value_label": "AO VIVO",
        }
        item["classification"] = probability_class(int(item["probability"])); item["opportunity_score"] = opportunity_score(item); out.append(item)
    def keep(x: dict[str, Any]) -> bool:
        if league and league.lower() not in str(x.get("league", "")).lower(): return False
        if market and market.lower() not in str(x.get("market", "")).lower(): return False
        if int(x.get("probability") or 0) < min_probability: return False
        if risk and risk.upper() != str(x.get("risk", "")).upper(): return False
        ev = x.get("ev_percent")
        if ev is not None and float(ev) < min_ev: return False
        if mode and mode.upper() != str(x.get("mode", "")).upper(): return False
        if value_only and "VALUE" not in str(x.get("value_label", "")).upper(): return False
        if strong_only and int(x.get("probability") or 0) < 80: return False
        return True
    return sorted([x for x in out if keep(x)], key=lambda x: x["opportunity_score"], reverse=True)[:50]


@router.get("/fixture/{fixture_id}/deep-analysis")
async def deep_analysis(fixture_id: int):
    try:
        return await DeepAnalysisService().fixture_context(fixture_id)
    except SportsApiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/stake")
def stake_suggestion(payload: StakeRequest, db: Session = Depends(get_db)):
    bankroll = db.get(Bankroll, 1)
    if bankroll is None:
        raise HTTPException(status_code=400, detail="Banca ainda não configurada")
    pending, exposure_pct, existing = _pending_exposure(db, bankroll)
    factor, correlation_message = correlation_penalty(existing, payload.model_dump())
    suggestion = dynamic_stake(
        bankroll=float(bankroll.current_value), unit_percent=float(bankroll.unit_percent), max_stake_percent=float(bankroll.max_stake_percent),
        probability=payload.probability, confidence=payload.confidence, ev_percent=payload.ev_percent, risk=payload.risk,
        drawdown_percent=max(0.0, payload.drawdown_percent), red_streak=max(0, payload.red_streak), current_exposure_percent=exposure_pct,
        correlation_factor=factor,
    )
    max_daily_entries = 5
    today = datetime.now(timezone.utc).date()
    todays = [t for t in db.scalars(select(BetTicket)).all() if t.created_at and t.created_at.date() == today]
    blocked = len(todays) >= max_daily_entries or exposure_pct >= 3.0
    return {**suggestion, "blocked": blocked, "daily_entries": len(todays), "daily_entry_limit": max_daily_entries, "pending_exposure": round(pending,2), "exposure_percent": round(exposure_pct,2), "exposure_limit_percent": 3.0, "correlation_factor": factor, "correlation_message": correlation_message}


@router.get("/model")
def model_info():
    report = recommendation_report()
    return {**model_metadata(), "calibration": report.get("calibration", [])}


@router.get("/calibration-panel")
def calibration_panel():
    report = recommendation_report()
    rows = []
    for item in report.get("calibration", []):
        gap = float(item.get("gap") or 0)
        trend = "superestimação" if gap < -2 else "subestimação" if gap > 2 else "calibrado"
        suggested = round(max(-10.0, min(5.0, gap)), 1)
        rows.append({**item, "trend": trend, "suggested_adjustment_pp": suggested, "sample_warning": item.get("samples",0) < 30})
    return {"model_version": MODEL_VERSION, "rows": rows, "policy": "Ajustes são conservadores e amostras pequenas não autorizam aumento de confiança."}


@router.post("/simulation")
def create_simulation(payload: SimulationCreate, db: Session = Depends(get_db)):
    row = SimulationBet(**payload.model_dump(), model_version=MODEL_VERSION)
    db.add(row); db.flush(); audit(db, "SIMULATION_CREATED", "simulation", str(row.id), "Aposta simulada registrada", payload.model_dump()); db.commit(); db.refresh(row)
    return _simulation_dict(row)


def _simulation_dict(row: SimulationBet) -> dict[str, Any]:
    return {"id": row.id, "fixture_id": row.fixture_id, "match_label": row.match_label, "league": row.league, "market": row.market, "selection": row.selection, "probability": row.probability, "confidence": row.confidence, "odd": row.odd, "stake_unit": row.stake_unit, "mode": row.mode, "result": row.result, "profit_unit": row.profit_unit, "model_version": row.model_version, "created_at": row.created_at}


@router.get("/simulation")
def list_simulation(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(SimulationBet).order_by(SimulationBet.created_at.desc())).all())
    settled = [r for r in rows if r.result in {"GREEN","RED","REFUND"}]
    profit = sum(r.profit_unit for r in settled); staked = sum(r.stake_unit for r in settled)
    wins = sum(1 for r in settled if r.result == "GREEN"); losses = sum(1 for r in settled if r.result == "RED")
    return {"rows": [_simulation_dict(r) for r in rows], "summary": {"entries": len(settled), "win_rate": round(wins/max(wins+losses,1)*100,2), "roi": round(profit/max(staked,1)*100,2), "profit_units": round(profit,2), "pending": sum(1 for r in rows if r.result == "PENDING")}}


@router.post("/simulation/sync")
async def sync_simulation(db: Session = Depends(get_db)):
    sports = SportsService(); checked = settled = waiting = errors = 0
    rows = list(db.scalars(select(SimulationBet).where(SimulationBet.result == "PENDING")).all())
    for row in rows:
        checked += 1
        try:
            match = await sports.final_match_data(row.fixture_id)
            if not match: waiting += 1; continue
            selection = row.selection.upper(); side = "OVER" if "OVER" in selection else "UNDER" if "UNDER" in selection else selection
            line = None
            for token in selection.replace(",", ".").split():
                try: line = float(token)
                except ValueError: pass
            market_id = "goals_ft" if "GOL" in row.market.upper() else "corners_ft" if "ESCANT" in row.market.upper() or "CORNER" in row.market.upper() else "double_chance" if "DUPLA" in row.market.upper() else ""
            result = settle_leg(market_id, side, line, row.odd, match)
            if result.status == "WAITING_STATS": waiting += 1; continue
            if result.status in {"WIN","HALF_WIN"}: row.result = "GREEN"
            elif result.status in {"LOSS","HALF_LOSS"}: row.result = "RED"
            else: row.result = "REFUND"
            row.profit_unit = round(row.stake_unit * float(result.multiplier or 0) - row.stake_unit, 3)
            row.settled_at = datetime.now(timezone.utc); settled += 1
        except Exception: errors += 1
    db.commit(); return {"checked": checked, "settled": settled, "waiting": waiting, "errors": errors}


@router.get("/reports/daily")
def daily_report(db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date(); rows = [r for r in db.scalars(select(BetEntryHistory)).all() if r.created_at and r.created_at.date() == today]
    return _report(rows, "daily", today.isoformat())


@router.get("/reports/weekly")
def weekly_report(db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date(); start = today - timedelta(days=6); rows = [r for r in db.scalars(select(BetEntryHistory)).all() if r.created_at and start <= r.created_at.date() <= today]
    return _report(rows, "weekly", f"{start.isoformat()}..{today.isoformat()}")


def _report(rows: list[BetEntryHistory], period: str, key: str) -> dict[str, Any]:
    total_staked = sum(float(r.stake) for r in rows); profit = sum(float(r.profit) for r in rows); greens = sum(1 for r in rows if r.result == "GREEN"); reds = sum(1 for r in rows if r.result == "RED")
    by_market: dict[str, list[BetEntryHistory]] = {}
    for r in rows: by_market.setdefault(r.market, []).append(r)
    market_rows = []
    for name, items in by_market.items():
        p = sum(float(x.profit) for x in items); s = sum(float(x.stake) for x in items); market_rows.append({"market": name, "entries": len(items), "profit": round(p,2), "roi": round(p/max(s,1)*100,2)})
    market_rows.sort(key=lambda x: x["roi"], reverse=True)
    return {"period": period, "key": key, "entries": len(rows), "greens": greens, "reds": reds, "profit": round(profit,2), "roi": round(profit/max(total_staked,1)*100,2), "best_market": market_rows[0] if market_rows else None, "worst_market": market_rows[-1] if market_rows else None, "markets": market_rows}


@router.get("/audit")
def audit_logs(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all())
    return [{"id": r.id, "event_type": r.event_type, "entity_type": r.entity_type, "entity_id": r.entity_id, "message": r.message, "payload": json.loads(r.payload_json or "{}"), "created_at": r.created_at} for r in rows]
