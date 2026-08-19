from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import current_user
from app.db.session import get_db
from app.models.entities import Bankroll
from app.schemas.bankroll import BankrollOut, BankrollUpsert

router = APIRouter(prefix="/bankroll", tags=["bankroll"], dependencies=[Depends(current_user)])


def serialize(row: Bankroll) -> BankrollOut:
    return BankrollOut(
        id=row.id,
        name=row.name,
        initial_value=row.initial_value,
        current_value=row.current_value,
        target_value=row.target_value,
        monthly_profit=row.monthly_profit,
        roi=row.roi,
        entries=row.entries,
        unit_percent=row.unit_percent,
        max_stake_percent=row.max_stake_percent,
        unit_value=row.current_value * row.unit_percent / 100,
        max_stake_value=row.current_value * row.max_stake_percent / 100,
        daily_loss_limit_value=row.current_value * row.daily_loss_limit_percent / 100,
        monthly_loss_limit_value=row.current_value * row.monthly_loss_limit_percent / 100,
    )


@router.get("", response_model=BankrollOut)
def read_bankroll(db: Session = Depends(get_db)):
    row = db.get(Bankroll, 1)
    if row is None:
        raise HTTPException(status_code=404, detail="Banca ainda não criada")
    return serialize(row)


@router.put("", response_model=BankrollOut)
def upsert_bankroll(payload: BankrollUpsert, db: Session = Depends(get_db)):
    row = db.get(Bankroll, 1)
    is_new = row is None
    if row is None:
        row = Bankroll(id=1)
        db.add(row)

    row.name = payload.name
    row.initial_value = payload.initial_value
    if is_new:
        row.current_value = payload.current_value if payload.current_value is not None else payload.initial_value
    elif payload.current_value is not None:
        row.current_value = payload.current_value

    row.target_value = payload.target_value
    row.unit_percent = payload.unit_percent
    row.max_stake_percent = payload.max_stake_percent
    row.daily_loss_limit_percent = payload.daily_loss_limit_percent
    row.monthly_loss_limit_percent = payload.monthly_loss_limit_percent

    db.commit()
    db.refresh(row)
    return serialize(row)
