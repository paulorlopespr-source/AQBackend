from pydantic import BaseModel, Field


class MethodIn(BaseModel):
    name: str
    description: str = ""
    win_rate: float = Field(default=0, ge=0, le=100)
    roi: float = 0
    entries: int = Field(default=0, ge=0)
    profit: float = 0
    avg_odd: float = Field(default=0, ge=0)
    max_drawdown: float = 0
    active: bool = True


class MethodOut(MethodIn):
    id: int
