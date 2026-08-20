from pydantic import BaseModel, Field


class EntryIn(BaseModel):
    id: str
    match: str
    market: str
    odd: float = Field(gt=1.0)
    stake: float = Field(ge=0)
    result: str
    profit: float = 0
    method: str = ""
    mode: str = "PRE_LIVE"


class EntryOut(EntryIn):
    pass
