from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Bankroll,
    BankrollMonthlySnapshot,
    BetEntryHistory,
    BetTicket,
    TicketStatus,
)


@dataclass
class MonthlyPerformance:
    month_key: str
    initial_value: float
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


def _month_bounds(now: datetime) -> tuple[datetime, datetime, str]:
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    last_day = monthrange(now.year, now.month)[1]
    end = datetime(now.year, now.month, last_day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    return start, end, f"{now.year:04d}-{now.month:02d}"


def calculate_monthly_performance(db: Session, bankroll: Bankroll) -> MonthlyPerformance:
    now = datetime.now(timezone.utc)
    start, end, month_key = _month_bounds(now)

    entries = list(
        db.scalars(
            select(BetEntryHistory)
            .where(BetEntryHistory.created_at >= start, BetEntryHistory.created_at <= end)
            .order_by(BetEntryHistory.created_at.asc())
        ).all()
    )

    total_staked = round(sum(max(float(entry.stake), 0.0) for entry in entries), 2)
    gross_profit = round(sum(max(float(entry.profit), 0.0) for entry in entries), 2)
    gross_loss = round(sum(abs(min(float(entry.profit), 0.0)) for entry in entries), 2)
    net_profit = round(gross_profit - gross_loss, 2)

    greens = sum(1 for entry in entries if entry.result.upper() == "GREEN")
    reds = sum(1 for entry in entries if entry.result.upper() == "RED")
    refunds = sum(1 for entry in entries if entry.result.upper() == "REFUND")

    snapshot = db.get(BankrollMonthlySnapshot, month_key)
    if snapshot is None:
        pending_statuses = {TicketStatus.PENDING.value, TicketStatus.WAITING_STATS.value}
        pending_tickets = db.scalars(
            select(BetTicket).where(
                BetTicket.created_at >= start,
                BetTicket.created_at <= end,
                BetTicket.status.in_(pending_statuses),
            )
        ).all()
        pending_stake = sum(float(ticket.stake) for ticket in pending_tickets)

        # current = início + lucro realizado - stakes ainda pendentes
        inferred_start = float(bankroll.current_value) - net_profit + pending_stake
        if inferred_start <= 0:
            inferred_start = float(bankroll.initial_value)

        snapshot = BankrollMonthlySnapshot(
            month_key=month_key,
            initial_value=round(max(inferred_start, 0.0), 2),
        )
        db.add(snapshot)
        db.flush()

    initial_value = float(snapshot.initial_value)

    # ROI operacional solicitado: lucro líquido / total apostado.
    roi = (net_profit / total_staked * 100.0) if total_staked > 0 else 0.0

    # Rentabilidade da banca no mês: lucro líquido / banca inicial mensal.
    bankroll_return = (net_profit / initial_value * 100.0) if initial_value > 0 else 0.0

    bankroll.monthly_profit = round(net_profit, 2)
    bankroll.roi = round(roi, 2)
    bankroll.entries = len(entries)

    return MonthlyPerformance(
        month_key=month_key,
        initial_value=round(initial_value, 2),
        total_staked=total_staked,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit=round(net_profit, 2),
        roi=round(roi, 2),
        bankroll_return=round(bankroll_return, 2),
        entries=len(entries),
        greens=greens,
        reds=reds,
        refunds=refunds,
    )


def refresh_monthly_performance(db: Session, bankroll: Bankroll) -> MonthlyPerformance:
    performance = calculate_monthly_performance(db, bankroll)
    db.flush()
    return performance
