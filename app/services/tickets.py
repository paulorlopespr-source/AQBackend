from __future__ import annotations

import uuid
from math import prod

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    Bankroll,
    BetTicket,
    TicketLeg,
    TicketStatus,
    LegStatus,
)
from app.schemas.ticket import TicketCreate
from app.services.bankroll import reserve_stake, apply_ticket_result
from app.services.risk import analyze_ticket
from app.services.settlement import settle_leg
from app.services.sports import SportsService


def get_bankroll(db: Session) -> Bankroll:
    bankroll = db.get(Bankroll, 1)
    if bankroll is None:
        bankroll = Bankroll(
            id=1,
            name="Banca Principal",
            initial_value=0,
            current_value=0,
        )
        db.add(bankroll)
        db.flush()
    return bankroll


def create_ticket(db: Session, payload: TicketCreate) -> BetTicket:
    bankroll = get_bankroll(db)
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

    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def ticket_by_id(db: Session, ticket_id: str) -> BetTicket | None:
    stmt = (
        select(BetTicket)
        .where(BetTicket.id == ticket_id)
        .options(selectinload(BetTicket.legs))
    )
    return db.scalars(stmt).first()


async def synchronize_ticket(db: Session, ticket: BetTicket, sports: SportsService) -> BetTicket:
    if ticket.status in {
        TicketStatus.GREEN.value,
        TicketStatus.RED.value,
        TicketStatus.REFUND.value,
    }:
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

    bankroll = get_bankroll(db)
    apply_ticket_result(bankroll, ticket)

    db.commit()
    db.refresh(ticket)
    return ticket
