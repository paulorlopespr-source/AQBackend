from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import current_user
from app.db.session import get_db
from app.models.entities import BettingMethod
from app.schemas.method import MethodIn, MethodOut

router = APIRouter(prefix="/methods", tags=["methods"], dependencies=[Depends(current_user)])


def out(row: BettingMethod) -> MethodOut:
    return MethodOut(
        id=row.id,
        name=row.name,
        description=row.description,
        win_rate=row.win_rate,
        roi=row.roi,
        entries=row.entries,
        profit=row.profit,
        avg_odd=row.avg_odd,
        max_drawdown=row.max_drawdown,
        active=row.active,
    )


@router.get("", response_model=list[MethodOut])
def list_methods(db: Session = Depends(get_db)):
    rows = db.scalars(select(BettingMethod).order_by(BettingMethod.profit.desc())).all()
    return [out(x) for x in rows]


@router.post("", response_model=MethodOut)
def create_method(payload: MethodIn, db: Session = Depends(get_db)):
    row = BettingMethod(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return out(row)


@router.put("/{method_id}", response_model=MethodOut)
def update_method(method_id: int, payload: MethodIn, db: Session = Depends(get_db)):
    row = db.get(BettingMethod, method_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Método não encontrado")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return out(row)


@router.delete("/{method_id}")
def delete_method(method_id: int, db: Session = Depends(get_db)):
    row = db.get(BettingMethod, method_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Método não encontrado")
    db.delete(row)
    db.commit()
    return {"deleted": True}
