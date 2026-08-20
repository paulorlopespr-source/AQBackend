from pydantic import BaseModel, Field


class TicketLegIn(BaseModel):
    fixture_id: int | None = None
    match_label: str
    market_id: str
    market_label: str
    selection_side: str = "OVER"
    line: float | None = None
    odd: float = Field(gt=1.0)
    estimated_probability: int = Field(ge=1, le=99)


class TicketCreate(BaseModel):
    stake: float = Field(gt=0)
    method_name: str = ""
    mode: str = "PRE_LIVE"
    legs: list[TicketLegIn] = Field(min_length=1)


class TicketLegOut(TicketLegIn):
    id: str
    result: str
    settlement_multiplier: float | None


class TicketOut(BaseModel):
    id: str
    stake: float
    total_odd: float
    estimated_probability: int
    risk_label: str
    risk_message: str
    status: str
    potential_return: float
    settled_return: float
    method_name: str = ""
    mode: str = "PRE_LIVE"
    legs: list[TicketLegOut]
