from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Bankroll, BankrollMonthlySnapshot, BetEntryHistory
from app.services.monthly_performance import calculate_monthly_performance


@dataclass
class MethodReport:
    method: str
    entries: int
    greens: int
    reds: int
    refunds: int
    total_staked: float
    profit: float
    roi: float
    win_rate: float


@dataclass
class DailyPoint:
    date: str
    entries: int
    staked: float
    profit: float
    cumulative_profit: float
    bankroll_value: float


@dataclass
class MonthlyReport:
    month_key: str
    initial_value: float
    current_realized_value: float
    total_staked: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    roi: float
    bankroll_return: float
    entries: int
    greens: int
    reds: int
    refunds: int
    max_green_streak: int
    max_red_streak: int
    best_method: MethodReport | None
    worst_method: MethodReport | None
    methods: list[MethodReport]
    daily_curve: list[DailyPoint]


def _month_entries(db: Session, month_key: str) -> list[BetEntryHistory]:
    year, month = [int(x) for x in month_key.split("-")]
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return list(
        db.scalars(
            select(BetEntryHistory)
            .where(BetEntryHistory.created_at >= start, BetEntryHistory.created_at < end)
            .order_by(BetEntryHistory.created_at.asc())
        ).all()
    )


def _streaks(entries: list[BetEntryHistory]) -> tuple[int, int]:
    green = red = max_green = max_red = 0
    for entry in entries:
        result = entry.result.upper()
        if result == "GREEN":
            green += 1
            red = 0
            max_green = max(max_green, green)
        elif result == "RED":
            red += 1
            green = 0
            max_red = max(max_red, red)
        else:
            # Reembolso é neutro e não aumenta nenhuma sequência.
            continue
    return max_green, max_red


def build_monthly_report(db: Session, bankroll: Bankroll) -> MonthlyReport:
    perf = calculate_monthly_performance(db, bankroll)
    entries = _month_entries(db, perf.month_key)

    grouped: dict[str, list[BetEntryHistory]] = defaultdict(list)
    for entry in entries:
        grouped[(entry.method or "Sem método").strip() or "Sem método"].append(entry)

    methods: list[MethodReport] = []
    for method_name, rows in grouped.items():
        staked = round(sum(max(float(x.stake), 0.0) for x in rows), 2)
        profit = round(sum(float(x.profit) for x in rows), 2)
        greens = sum(1 for x in rows if x.result.upper() == "GREEN")
        reds = sum(1 for x in rows if x.result.upper() == "RED")
        refunds = sum(1 for x in rows if x.result.upper() == "REFUND")
        decided = greens + reds
        methods.append(
            MethodReport(
                method=method_name,
                entries=len(rows),
                greens=greens,
                reds=reds,
                refunds=refunds,
                total_staked=staked,
                profit=profit,
                roi=round((profit / staked * 100.0) if staked > 0 else 0.0, 2),
                win_rate=round((greens / decided * 100.0) if decided > 0 else 0.0, 2),
            )
        )

    methods.sort(key=lambda x: (x.roi, x.profit), reverse=True)
    eligible = [x for x in methods if x.entries > 0]
    best_method = eligible[0] if eligible else None
    worst_method = min(eligible, key=lambda x: (x.roi, x.profit)) if eligible else None

    daily = defaultdict(lambda: {"entries": 0, "staked": 0.0, "profit": 0.0})
    for entry in entries:
        key = entry.created_at.astimezone(timezone.utc).date().isoformat()
        daily[key]["entries"] += 1
        daily[key]["staked"] += float(entry.stake)
        daily[key]["profit"] += float(entry.profit)

    cumulative = 0.0
    curve: list[DailyPoint] = []
    for date_key in sorted(daily.keys()):
        values = daily[date_key]
        day_profit = round(values["profit"], 2)
        cumulative = round(cumulative + day_profit, 2)
        curve.append(
            DailyPoint(
                date=date_key,
                entries=int(values["entries"]),
                staked=round(values["staked"], 2),
                profit=day_profit,
                cumulative_profit=cumulative,
                bankroll_value=round(perf.initial_value + cumulative, 2),
            )
        )

    max_green, max_red = _streaks(entries)

    return MonthlyReport(
        month_key=perf.month_key,
        initial_value=perf.initial_value,
        current_realized_value=round(perf.initial_value + perf.net_profit, 2),
        total_staked=perf.total_staked,
        gross_profit=perf.gross_profit,
        gross_loss=perf.gross_loss,
        net_profit=perf.net_profit,
        roi=perf.roi,
        bankroll_return=perf.bankroll_return,
        entries=perf.entries,
        greens=perf.greens,
        reds=perf.reds,
        refunds=perf.refunds,
        max_green_streak=max_green,
        max_red_streak=max_red,
        best_method=best_method,
        worst_method=worst_method,
        methods=methods,
        daily_curve=curve,
    )
