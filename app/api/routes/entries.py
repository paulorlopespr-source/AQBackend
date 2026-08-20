from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import current_user
from app.db.session import get_db
from app.models.entities import BetEntryHistory
from app.schemas.entry import EntryIn, EntryOut
from app.services.method_performance import refresh_method_by_name

router = APIRouter(prefix="/entries", tags=["entries"], dependencies=[Depends(current_user)])


def out(row: BetEntryHistory) -> EntryOut:
    return EntryOut(
        id=row.id,
        match=row.match,
        market=row.market,
        odd=row.odd,
        stake=row.stake,
        result=row.result,
        profit=row.profit,
        method=row.method,
        mode=row.mode,
    )


@router.get("", response_model=list[EntryOut])
def list_entries(db: Session = Depends(get_db)):
    rows = db.scalars(select(BetEntryHistory).order_by(BetEntryHistory.created_at.desc())).all()
    return [out(row) for row in rows]


@router.post("", response_model=EntryOut)
def upsert_entry(payload: EntryIn, db: Session = Depends(get_db)):
    row = db.get(BetEntryHistory, payload.id)
    previous_method = row.method if row is not None else ""

    if row is None:
        row = BetEntryHistory(id=payload.id)
        db.add(row)
    for key, value in payload.model_dump().items():
        if key != "id":
            setattr(row, key, value)

    db.flush()
    if previous_method and previous_method.lower() != row.method.lower():
        refresh_method_by_name(db, previous_method)
    refresh_method_by_name(db, row.method)
    db.commit()
    db.refresh(row)
    return out(row)


@router.delete("/{entry_id}")
def delete_entry(entry_id: str, db: Session = Depends(get_db)):
    row = db.get(BetEntryHistory, entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")
    method_name = row.method
    db.delete(row)
    db.flush()
    refresh_method_by_name(db, method_name)
    db.commit()
    return {"deleted": True}
