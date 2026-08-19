from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import current_user
from app.db.session import get_db
from app.models.entities import BetTicket
from app.schemas.ticket import TicketCreate, TicketLegOut, TicketOut
from app.services.risk import analyze_ticket
from app.services.sports import SportsService
from app.services.tickets import create_ticket, synchronize_ticket, ticket_by_id

router = APIRouter(prefix="/tickets", tags=["tickets"], dependencies=[Depends(current_user)])


def serialize(ticket: BetTicket) -> TicketOut:
    risk = analyze_ticket([leg.estimated_probability for leg in ticket.legs])
    return TicketOut(
        id=ticket.id,
        stake=ticket.stake,
        total_odd=ticket.total_odd,
        estimated_probability=ticket.estimated_probability,
        risk_label=ticket.risk_label,
        risk_message=risk["message"],
        status=ticket.status,
        potential_return=ticket.potential_return,
        settled_return=ticket.settled_return,
        legs=[
            TicketLegOut(
                id=leg.id,
                fixture_id=leg.fixture_id,
                match_label=leg.match_label,
                market_id=leg.market_id,
                market_label=leg.market_label,
                selection_side=leg.selection_side,
                line=leg.line,
                odd=leg.odd,
                estimated_probability=leg.estimated_probability,
                result=leg.result,
                settlement_multiplier=leg.settlement_multiplier,
            )
            for leg in ticket.legs
        ],
    )


@router.post("", response_model=TicketOut)
def create(payload: TicketCreate, db: Session = Depends(get_db)):
    try:
        ticket = create_ticket(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ticket = ticket_by_id(db, ticket.id)
    return serialize(ticket)


@router.get("", response_model=list[TicketOut])
def list_tickets(db: Session = Depends(get_db)):
    stmt = (
        select(BetTicket)
        .options(selectinload(BetTicket.legs))
        .order_by(BetTicket.created_at.desc())
    )
    return [serialize(x) for x in db.scalars(stmt).all()]


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str, db: Session = Depends(get_db)):
    ticket = ticket_by_id(db, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Bilhete não encontrado")
    return serialize(ticket)


@router.post("/{ticket_id}/sync", response_model=TicketOut)
async def sync_ticket(ticket_id: str, db: Session = Depends(get_db)):
    ticket = ticket_by_id(db, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Bilhete não encontrado")
    await synchronize_ticket(db, ticket, SportsService())
    ticket = ticket_by_id(db, ticket_id)
    return serialize(ticket)
