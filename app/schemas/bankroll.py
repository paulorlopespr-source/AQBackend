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
    month_key: str
    monthly_initial_value: float
    monthly_total_staked: float
    monthly_gross_profit: float
    monthly_gross_loss: float
    monthly_bankroll_return: float
    monthly_greens: int
    monthly_reds: int
    monthly_refunds: int


class DailyRiskOut(BaseModel):
    date: str
    bankroll_value: float
    unit_value: float
    max_stake_value: float
    daily_loss_limit_value: float
    realized_loss: float
    realized_profit: float
    net_profit: float
    total_staked: float
    pending_stake: float
    daily_entries: int
    greens: int
    reds: int
    refunds: int
    current_red_streak: int
    stop_remaining: float
    risk_status: str
    risk_message: str
    suggested_stake: float


class DailyBankrollPointOut(BaseModel):
    date: str
    entries: int
    staked: float
    profit: float
    cumulative_profit: float
    bankroll_value: float


class MethodMonthlyPerformanceOut(BaseModel):
    method: str
    entries: int
    greens: int
    reds: int
    refunds: int
    total_staked: float
    profit: float
    roi: float
    win_rate: float


class MonthlyBankrollReportOut(BaseModel):
    month_key: str
    initial_value: float
    current_realized_value: float
    total_staked: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    roi: float
    bankroll_return: float
    entries: int
    greens: int
    reds: int
    refunds: int
    max_green_streak: int
    max_red_streak: int
    best_method: MethodMonthlyPerformanceOut | None
    worst_method: MethodMonthlyPerformanceOut | None
    methods: list[MethodMonthlyPerformanceOut]
    daily_curve: list[DailyBankrollPointOut]
