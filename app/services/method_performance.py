from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import BetEntryHistory, BettingMethod


def _entries_for_method(db: Session, method_name: str) -> list[BetEntryHistory]:
    stmt = (
        select(BetEntryHistory)
        .where(func.lower(BetEntryHistory.method) == method_name.strip().lower())
        .order_by(BetEntryHistory.created_at.asc())
    )
    return list(db.scalars(stmt).all())


def refresh_method_performance(db: Session, method: BettingMethod) -> BettingMethod:
    entries = _entries_for_method(db, method.name)

    if not entries:
        method.win_rate = 0
        method.roi = 0
        method.entries = 0
        method.profit = 0
        method.avg_odd = 0
        method.max_drawdown = 0
        return method

    total_stake = sum(max(float(entry.stake), 0.0) for entry in entries)
    total_profit = sum(float(entry.profit) for entry in entries)
    avg_odd = sum(float(entry.odd) for entry in entries) / len(entries)

    decided = [entry for entry in entries if entry.result.upper() in {"GREEN", "RED"}]
    greens = sum(1 for entry in decided if entry.result.upper() == "GREEN")
    win_rate = (greens / len(decided) * 100.0) if decided else 0.0
    roi = (total_profit / total_stake * 100.0) if total_stake > 0 else 0.0

    # Drawdown do método baseado na curva acumulada de lucro/prejuízo.
    equity = 0.0
    peak = 0.0
    max_drawdown_value = 0.0
    for entry in entries:
        equity += float(entry.profit)
        peak = max(peak, equity)
        max_drawdown_value = max(max_drawdown_value, peak - equity)

    max_drawdown_percent = (max_drawdown_value / total_stake * 100.0) if total_stake > 0 else 0.0

    method.win_rate = round(win_rate, 2)
    method.roi = round(roi, 2)
    method.entries = len(entries)
    method.profit = round(total_profit, 2)
    method.avg_odd = round(avg_odd, 2)
    method.max_drawdown = round(-max_drawdown_percent, 2) if max_drawdown_percent > 0 else 0.0
    return method


def refresh_method_by_name(db: Session, method_name: str) -> None:
    if not method_name.strip():
        return
    stmt = select(BettingMethod).where(func.lower(BettingMethod.name) == method_name.strip().lower())
    method = db.scalars(stmt).first()
    if method is not None:
        refresh_method_performance(db, method)


def refresh_all_methods(db: Session) -> None:
    methods = db.scalars(select(BettingMethod)).all()
    for method in methods:
        refresh_method_performance(db, method)
