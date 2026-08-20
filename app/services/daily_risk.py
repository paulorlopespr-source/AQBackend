from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Bankroll, BetEntryHistory, BetTicket, TicketStatus


@dataclass
class DailyRisk:
    date: str
    bankroll_value: float
    unit_value: float
    max_stake_value: float
    daily_loss_limit_value: float
    realized_loss: float
    realized_profit: float
    net_profit: float
    total_staked: float
    pending_stake: float
    daily_entries: int
    greens: int
    reds: int
    refunds: int
    current_red_streak: int
    stop_remaining: float
    risk_status: str
    risk_message: str
    suggested_stake: float


def calculate_daily_risk(db: Session, bankroll: Bankroll) -> DailyRisk:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    entries = list(
        db.scalars(
            select(BetEntryHistory)
            .where(BetEntryHistory.created_at >= start)
            .order_by(BetEntryHistory.created_at.asc())
        ).all()
    )

    total_staked = round(sum(max(float(x.stake), 0.0) for x in entries), 2)
    realized_profit = round(sum(max(float(x.profit), 0.0) for x in entries), 2)
    realized_loss = round(sum(abs(min(float(x.profit), 0.0)) for x in entries), 2)
    net_profit = round(realized_profit - realized_loss, 2)

    greens = sum(1 for x in entries if x.result.upper() == "GREEN")
    reds = sum(1 for x in entries if x.result.upper() == "RED")
    refunds = sum(1 for x in entries if x.result.upper() == "REFUND")

    red_streak = 0
    for entry in reversed(entries):
        result = entry.result.upper()
        if result == "RED":
            red_streak += 1
        elif result == "REFUND":
            continue
        else:
            break

    pending_statuses = {TicketStatus.PENDING.value, TicketStatus.WAITING_STATS.value}
    pending_tickets = db.scalars(
        select(BetTicket).where(
            BetTicket.created_at >= start,
            BetTicket.status.in_(pending_statuses),
        )
    ).all()
    pending_stake = round(sum(float(x.stake) for x in pending_tickets), 2)

    bankroll_value = max(float(bankroll.current_value), 0.0)
    unit_value = round(bankroll_value * float(bankroll.unit_percent) / 100.0, 2)
    max_stake_value = round(bankroll_value * float(bankroll.max_stake_percent) / 100.0, 2)
    daily_limit = round(bankroll_value * float(bankroll.daily_loss_limit_percent) / 100.0, 2)
    stop_remaining = round(max(daily_limit - realized_loss, 0.0), 2)

    usage = (realized_loss / daily_limit) if daily_limit > 0 else 0.0
    if daily_limit > 0 and realized_loss >= daily_limit:
        status = "STOP"
        message = "Stop-loss diário atingido. Novas entradas devem permanecer bloqueadas até o próximo dia."
        suggested_stake = 0.0
    elif usage >= 0.75 or red_streak >= 3:
        status = "ALERT"
        message = "Risco diário elevado. Reduza exposição e evite aumentar stake para recuperar perdas."
        suggested_stake = min(unit_value * 0.5, max_stake_value, stop_remaining)
    elif usage >= 0.50 or red_streak >= 2:
        status = "CAUTION"
        message = "Atenção à sequência e ao consumo do stop diário. Priorize somente entradas do método."
        suggested_stake = min(unit_value * 0.75, max_stake_value, stop_remaining)
    else:
        status = "NORMAL"
        message = "Gestão diária dentro dos limites configurados."
        suggested_stake = min(unit_value, max_stake_value, stop_remaining if daily_limit > 0 else unit_value)

    return DailyRisk(
        date=now.date().isoformat(),
        bankroll_value=round(bankroll_value, 2),
        unit_value=unit_value,
        max_stake_value=max_stake_value,
        daily_loss_limit_value=daily_limit,
        realized_loss=realized_loss,
        realized_profit=realized_profit,
        net_profit=net_profit,
        total_staked=total_staked,
        pending_stake=pending_stake,
        daily_entries=len(entries),
        greens=greens,
        reds=reds,
        refunds=refunds,
        current_red_streak=red_streak,
        stop_remaining=stop_remaining,
        risk_status=status,
        risk_message=message,
        suggested_stake=round(max(suggested_stake, 0.0), 2),
    )
