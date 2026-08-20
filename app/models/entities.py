from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TicketStatus(StrEnum):
    PENDING = "PENDING"
    WAITING_STATS = "WAITING_STATS"
    GREEN = "GREEN"
    RED = "RED"
    REFUND = "REFUND"
    PARTIAL = "PARTIAL"


class LegStatus(StrEnum):
    PENDING = "PENDING"
    WAITING_STATS = "WAITING_STATS"
    WIN = "WIN"
    LOSS = "LOSS"
    PUSH = "PUSH"
    HALF_WIN = "HALF_WIN"
    HALF_LOSS = "HALF_LOSS"


class Bankroll(Base):
    __tablename__ = "bankrolls"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(100), default="Banca Principal")
    initial_value: Mapped[float] = mapped_column(Float, default=0)
    current_value: Mapped[float] = mapped_column(Float, default=0)
    target_value: Mapped[float] = mapped_column(Float, default=0)
    monthly_profit: Mapped[float] = mapped_column(Float, default=0)
    roi: Mapped[float] = mapped_column(Float, default=0)
    entries: Mapped[int] = mapped_column(Integer, default=0)

    unit_percent: Mapped[float] = mapped_column(Float, default=1.0)
    max_stake_percent: Mapped[float] = mapped_column(Float, default=2.5)
    daily_loss_limit_percent: Mapped[float] = mapped_column(Float, default=5.0)
    monthly_loss_limit_percent: Mapped[float] = mapped_column(Float, default=15.0)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BankrollMonthlySnapshot(Base):
    __tablename__ = "bankroll_monthly_snapshots"

    month_key: Mapped[str] = mapped_column(String(7), primary_key=True)
    initial_value: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BettingMethod(Base):
    __tablename__ = "betting_methods"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(String(1000), default="")
    win_rate: Mapped[float] = mapped_column(Float, default=0)
    roi: Mapped[float] = mapped_column(Float, default=0)
    entries: Mapped[int] = mapped_column(Integer, default=0)
    profit: Mapped[float] = mapped_column(Float, default=0)
    avg_odd: Mapped[float] = mapped_column(Float, default=0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BetEntryHistory(Base):
    __tablename__ = "bet_entry_history"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    match: Mapped[str] = mapped_column(String(250))
    market: Mapped[str] = mapped_column(String(250))
    odd: Mapped[float] = mapped_column(Float)
    stake: Mapped[float] = mapped_column(Float)
    result: Mapped[str] = mapped_column(String(20))
    profit: Mapped[float] = mapped_column(Float, default=0)
    method: Mapped[str] = mapped_column(String(150), default="")
    mode: Mapped[str] = mapped_column(String(30), default="PRE_LIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BetTicket(Base):
    __tablename__ = "bet_tickets"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stake: Mapped[float] = mapped_column(Float)
    total_odd: Mapped[float] = mapped_column(Float)
    estimated_probability: Mapped[int] = mapped_column(Integer)
    risk_label: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default=TicketStatus.PENDING.value)
    potential_return: Mapped[float] = mapped_column(Float)
    settled_return: Mapped[float] = mapped_column(Float, default=0)
    bankroll_applied: Mapped[bool] = mapped_column(Boolean, default=False)

    legs: Mapped[list["TicketLeg"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class TicketMethodContext(Base):
    __tablename__ = "ticket_method_context"

    ticket_id: Mapped[str] = mapped_column(
        ForeignKey("bet_tickets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    method_name: Mapped[str] = mapped_column(String(150), default="")
    mode: Mapped[str] = mapped_column(String(30), default="PRE_LIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TicketLeg(Base):
    __tablename__ = "ticket_legs"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("bet_tickets.id", ondelete="CASCADE"), index=True)

    fixture_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    match_label: Mapped[str] = mapped_column(String(250))
    market_id: Mapped[str] = mapped_column(String(120))
    market_label: Mapped[str] = mapped_column(String(250))
    selection_side: Mapped[str] = mapped_column(String(30), default="OVER")
    line: Mapped[float | None] = mapped_column(Float, nullable=True)
    odd: Mapped[float] = mapped_column(Float)
    estimated_probability: Mapped[int] = mapped_column(Integer)

    result: Mapped[str] = mapped_column(String(30), default=LegStatus.PENDING.value)
    settlement_multiplier: Mapped[float | None] = mapped_column(Float, nullable=True)

    ticket: Mapped["BetTicket"] = relationship(back_populates="legs")


class SportsFixtureCache(Base):
    __tablename__ = "sports_fixture_cache"

    fixture_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league: Mapped[str] = mapped_column(String(150), default="")
    kickoff: Mapped[str] = mapped_column(String(80), default="")
    home_team_id: Mapped[int] = mapped_column(Integer)
    home_team: Mapped[str] = mapped_column(String(150))
    away_team_id: Mapped[int] = mapped_column(Integer)
    away_team: Mapped[str] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(20), default="NS")
    home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked: Mapped[int] = mapped_column(Integer, default=0)
    settled: Mapped[int] = mapped_column(Integer, default=0)
    waiting: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(1000), default="")
