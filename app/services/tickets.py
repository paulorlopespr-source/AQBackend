from __future__ import annotations

import uuid
from datetime import datetime, timezone
from math import prod

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    Bankroll,
    BetEntryHistory,
    BetTicket,
    TicketLeg,
    TicketMethodContext,
    TicketStatus,
    LegStatus,
)
from app.schemas.ticket import TicketCreate
from app.services.bankroll import reserve_stake, apply_ticket_result
from app.services.daily_risk import calculate_daily_risk
from app.services.method_performance import refresh_method_by_name
from app.services.monthly_performance import refresh_monthly_performance
from app.services.risk import analyze_ticket
from app.services.settlement import settle_leg
from app.services.sports import SportsService


def get_bankroll(db: Session) -> Bankroll:
    bankroll = db.get(Bankroll, 1)
    if bankroll is None:
        bankroll = Bankroll(id=1, name="Banca Principal", initial_value=0, current_value=0)
        db.add(bankroll)
        db.flush()
    return bankroll


def _daily_realized_loss(db: Session) -> float:
    today = datetime.now(timezone.utc).date()
    tickets = db.scalars(select(BetTicket)).all()
    loss = 0.0
    for ticket in tickets:
        created = ticket.created_at
        if created is None or created.date() != today:
            continue
        if ticket.status not in {
            TicketStatus.GREEN.value,
            TicketStatus.RED.value,
            TicketStatus.REFUND.value,
            TicketStatus.PARTIAL.value,
        }:
            continue
        result = float(ticket.settled_return) - float(ticket.stake)
        if result < 0:
            loss += abs(result)
    return loss


def _validate_bankroll_limits(db: Session, bankroll: Bankroll, stake: float) -> None:
    if bankroll.current_value <= 0:
        raise ValueError("Banca sem saldo disponível")

    risk = calculate_daily_risk(db, bankroll)
    if risk.risk_status == "STOP":
        raise ValueError(
            "Entrada bloqueada: stop-loss diário atingido. "
            "Novas apostas ficam bloqueadas até o próximo dia."
        )

    max_stake = bankroll.current_value * bankroll.max_stake_percent / 100
    if stake > max_stake + 1e-9:
        raise ValueError(
            f"Stake acima do limite da banca. Máximo atual: R$ {max_stake:.2f} "
            f"({bankroll.max_stake_percent:.2f}%)"
        )

    if risk.daily_loss_limit_value > 0 and stake > risk.stop_remaining + 1e-9:
        raise ValueError(
            f"Entrada bloqueada: esta stake pode ultrapassar o stop diário. "
            f"Margem restante: R$ {risk.stop_remaining:.2f}."
        )

    perf = refresh_monthly_performance(db, bankroll)
    monthly_limit = perf.initial_value * bankroll.monthly_loss_limit_percent / 100
    monthly_loss = max(0.0, -perf.net_profit)
    if monthly_loss >= monthly_limit and monthly_limit > 0:
        raise ValueError(f"Stop-loss mensal atingido. Perda acumulada no mês: R$ {monthly_loss:.2f}")


def _history_result(ticket: BetTicket) -> str:
    if ticket.status == TicketStatus.GREEN.value:
        return "GREEN"
    if ticket.status == TicketStatus.RED.value:
        return "RED"
    if ticket.status == TicketStatus.REFUND.value:
        return "REFUND"
    profit = float(ticket.settled_return) - float(ticket.stake)
    if profit > 1e-9:
        return "GREEN"
    if profit < -1e-9:
        return "RED"
    return "REFUND"


def _fallback_history_method(ticket: BetTicket) -> str:
    if len(ticket.legs) == 1:
        return ticket.legs[0].market_label or ticket.legs[0].market_id
    return "Múltipla AQ"


def _history_context(db: Session, ticket: BetTicket) -> tuple[str, str]:
    context = db.get(TicketMethodContext, ticket.id)
    if context is None:
        return _fallback_history_method(ticket), "PRE_LIVE"
    method_name = context.method_name.strip() or _fallback_history_method(ticket)
    mode = context.mode.upper() if context.mode.upper() in {"PRE_LIVE", "LIVE"} else "PRE_LIVE"
    return method_name, mode


def _history_market(ticket: BetTicket) -> str:
    labels = []
    for leg in ticket.legs:
        side = leg.selection_side or ""
        line = "" if leg.line is None else f" {leg.line:g}"
        labels.append(f"{leg.market_label}: {side}{line}".strip())
    return " | ".join(labels)


def _history_match(ticket: BetTicket) -> str:
    labels = list(dict.fromkeys(leg.match_label for leg in ticket.legs if leg.match_label))
    return " | ".join(labels)


def _sync_ticket_history(db: Session, ticket: BetTicket) -> None:
    if ticket.status not in {
        TicketStatus.GREEN.value,
        TicketStatus.RED.value,
        TicketStatus.REFUND.value,
        TicketStatus.PARTIAL.value,
    }:
        return

    entry_id = f"ticket:{ticket.id}"
    row = db.get(BetEntryHistory, entry_id)
    if row is None:
        row = BetEntryHistory(id=entry_id)
        db.add(row)

    method_name, mode = _history_context(db, ticket)
    row.match = _history_match(ticket)
    row.market = _history_market(ticket)
    row.odd = float(ticket.total_odd)
    row.stake = float(ticket.stake)
    row.result = _history_result(ticket)
    row.profit = round(float(ticket.settled_return) - float(ticket.stake), 2)
    row.method = method_name
    row.mode = mode
    db.flush()
    refresh_method_by_name(db, method_name)


def create_ticket(db: Session, payload: TicketCreate) -> BetTicket:
    bankroll = get_bankroll(db)
    _validate_bankroll_limits(db, bankroll, payload.stake)
    reserve_stake(bankroll, payload.stake)

    leg_probs = [leg.estimated_probability for leg in payload.legs]
    risk = analyze_ticket(leg_probs)
    total_odd = prod(leg.odd for leg in payload.legs)

    ticket_id = str(uuid.uuid4())
    ticket = BetTicket(
        id=ticket_id,
        stake=payload.stake,
        total_odd=total_odd,
        estimated_probability=risk["probability"],
        risk_label=risk["risk_label"],
        status=TicketStatus.PENDING.value,
        potential_return=payload.stake * total_odd,
        settled_return=0,
    )

    ticket.legs = [
        TicketLeg(
            id=str(uuid.uuid4()),
            ticket_id=ticket_id,
            fixture_id=leg.fixture_id,
            match_label=leg.match_label,
            market_id=leg.market_id,
            market_label=leg.market_label,
            selection_side=leg.selection_side.upper(),
            line=leg.line,
            odd=leg.odd,
            estimated_probability=leg.estimated_probability,
            result=LegStatus.PENDING.value,
        )
        for leg in payload.legs
    ]

    mode = payload.mode.upper() if payload.mode.upper() in {"PRE_LIVE", "LIVE"} else "PRE_LIVE"
    context = TicketMethodContext(
        ticket_id=ticket_id,
        method_name=payload.method_name.strip(),
        mode=mode,
    )

    db.add(ticket)
    db.add(context)
    db.commit()
    db.refresh(ticket)
    return ticket


def ticket_by_id(db: Session, ticket_id: str) -> BetTicket | None:
    stmt = select(BetTicket).where(BetTicket.id == ticket_id).options(selectinload(BetTicket.legs))
    return db.scalars(stmt).first()


def delete_ticket(db: Session, ticket: BetTicket) -> None:
    bankroll = get_bankroll(db)
    method_name, _ = _history_context(db, ticket)

    bankroll.current_value += float(ticket.stake)
    if ticket.bankroll_applied:
        bankroll.current_value -= float(ticket.settled_return)

    history = db.get(BetEntryHistory, f"ticket:{ticket.id}")
    if history is not None:
        db.delete(history)
        db.flush()

    context = db.get(TicketMethodContext, ticket.id)
    if context is not None:
        db.delete(context)
        db.flush()

    db.delete(ticket)
    db.flush()
    refresh_method_by_name(db, method_name)
    refresh_monthly_performance(db, bankroll)
    db.commit()


async def synchronize_ticket(db: Session, ticket: BetTicket, sports: SportsService) -> BetTicket:
    bankroll = get_bankroll(db)

    if ticket.status in {
        TicketStatus.GREEN.value,
        TicketStatus.RED.value,
        TicketStatus.REFUND.value,
        TicketStatus.PARTIAL.value,
    }:
        _sync_ticket_history(db, ticket)
        refresh_monthly_performance(db, bankroll)
        db.commit()
        return ticket

    for leg in ticket.legs:
        if leg.result in {
            LegStatus.WIN.value,
            LegStatus.LOSS.value,
            LegStatus.PUSH.value,
            LegStatus.HALF_WIN.value,
            LegStatus.HALF_LOSS.value,
        }:
            continue

        if leg.fixture_id is None:
            leg.result = LegStatus.WAITING_STATS.value
            continue

        match = await sports.final_match_data(leg.fixture_id)
        if match is None:
            leg.result = LegStatus.WAITING_STATS.value
            continue

        settlement = settle_leg(
            market_id=leg.market_id,
            side=leg.selection_side,
            line=leg.line,
            odd=leg.odd,
            match=match,
        )
        leg.result = settlement.status
        leg.settlement_multiplier = settlement.multiplier

    statuses = [leg.result for leg in ticket.legs]

    if any(x == LegStatus.LOSS.value for x in statuses):
        ticket.status = TicketStatus.RED.value
        ticket.settled_return = 0
    elif any(x in {LegStatus.PENDING.value, LegStatus.WAITING_STATS.value} for x in statuses):
        ticket.status = TicketStatus.WAITING_STATS.value
    else:
        multipliers = [leg.settlement_multiplier for leg in ticket.legs]
        if any(x is None for x in multipliers):
            ticket.status = TicketStatus.WAITING_STATS.value
        else:
            effective_odd = prod(float(x) for x in multipliers)
            ticket.settled_return = ticket.stake * effective_odd

            if all(x == LegStatus.PUSH.value for x in statuses):
                ticket.status = TicketStatus.REFUND.value
            elif any(x in {LegStatus.HALF_WIN.value, LegStatus.HALF_LOSS.value, LegStatus.PUSH.value} for x in statuses):
                ticket.status = TicketStatus.PARTIAL.value
            else:
                ticket.status = TicketStatus.GREEN.value

    apply_ticket_result(bankroll, ticket)
    _sync_ticket_history(db, ticket)
    refresh_monthly_performance(db, bankroll)

    db.commit()
    db.refresh(ticket)
    return ticket
