from pydantic import BaseModel, Field


class BankrollUpsert(BaseModel):
    name: str = "Banca Principal"
    initial_value: float = Field(ge=0)
    current_value: float | None = Field(default=None, ge=0)
    target_value: float = Field(default=0, ge=0)
    unit_percent: float = Field(default=1.0, gt=0, le=100)
    max_stake_percent: float = Field(default=2.5, gt=0, le=100)
    daily_loss_limit_percent: float = Field(default=5.0, gt=0, le=100)
    monthly_loss_limit_percent: float = Field(default=15.0, gt=0, le=100)


class BankrollOut(BaseModel):
    id: int
    name: str
    initial_value: float
    current_value: float
    target_value: float
    monthly_profit: float
    roi: float
    entries: int
    unit_percent: float
    max_stake_percent: float
    unit_value: float
    max_stake_value: float
    daily_loss_limit_value: float
    monthly_loss_limit_value: float
