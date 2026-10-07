from __future__ import annotations

from datetime import date, datetime, time
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .team import Team

class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)  # fixed | rotation
    weekdays: Mapped[str] = mapped_column(String(30), nullable=False)  # comma-separated 0..6
    # When the shift runs, in the bar's local time. An end at or before the start means the next day.
    start_time: Mapped[time] = mapped_column(Time, default=time(20, 30), nullable=False)
    end_time: Mapped[time] = mapped_column(Time, default=time(23, 59), nullable=False)
    requires_manager_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rotation_anchor_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    rotation_members: Mapped[list[RotationMember]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", order_by="RotationMember.position"
    )
    pattern_days: Mapped[list[MonthlyPattern]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", order_by="MonthlyPattern.day_of_month"
    )

    @property
    def weekday_set(self) -> set[int]:
        return {int(v) for v in self.weekdays.split(",") if v.strip()}


class MonthlyPattern(Base):
    """One team per calendar day of the month, repeating every month."""

    __tablename__ = "monthly_patterns"
    __table_args__ = (
        UniqueConstraint("schedule_id", "day_of_month", name="uq_pattern_schedule_day"),
        CheckConstraint("day_of_month BETWEEN 1 AND 31", name="ck_pattern_day_of_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False)
    day_of_month: Mapped[int] = mapped_column(Integer, nullable=False)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)

    schedule: Mapped[Schedule] = relationship(back_populates="pattern_days")
    team: Mapped[Team | None] = relationship()


class RotationMember(Base):
    __tablename__ = "rotation_members"
    __table_args__ = (
        UniqueConstraint("schedule_id", "team_id", name="uq_rotation_schedule_team"),
        UniqueConstraint("schedule_id", "position", name="uq_rotation_schedule_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    schedule: Mapped[Schedule] = relationship(back_populates="rotation_members")
    team: Mapped[Team] = relationship()
