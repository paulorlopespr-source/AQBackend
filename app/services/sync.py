from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.entities import BetTicket, SyncRun, TicketStatus
from app.services.sports import SportsService
from app.services.tickets import synchronize_ticket


async def sync_pending_tickets() -> dict:
    sports = SportsService()
    db = SessionLocal()
    run = SyncRun()
    db.add(run)
    db.commit()
    db.refresh(run)

    checked = settled = waiting = errors = 0

    try:
        stmt = (
            select(BetTicket)
            .where(BetTicket.status.in_([
                TicketStatus.PENDING.value,
                TicketStatus.WAITING_STATS.value,
            ]))
            .options(selectinload(BetTicket.legs))
        )
        tickets = list(db.scalars(stmt).all())

        for ticket in tickets:
            checked += 1
            try:
                before = ticket.status
                await synchronize_ticket(db, ticket, sports)
                if ticket.status in {
                    TicketStatus.GREEN.value,
                    TicketStatus.RED.value,
                    TicketStatus.REFUND.value,
                    TicketStatus.PARTIAL.value,
                }:
                    settled += 1
                else:
                    waiting += 1
            except Exception:
                db.rollback()
                errors += 1

        run.checked = checked
        run.settled = settled
        run.waiting = waiting
        run.errors = errors
        run.message = "Sincronização concluída"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "checked": checked,
            "settled": settled,
            "waiting": waiting,
            "errors": errors,
        }
    finally:
        db.close()
