from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    """A login: a username, a password and the administrator flag. Several teams can be
    assigned to it, so one person can sign in once and control the shifts of all of them."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    teams: Mapped[list[Team]] = relationship(back_populates="user")

    @property
    def can_login(self) -> bool:
        return bool(self.username and self.password_hash)

    @property
    def label(self) -> str:
        return self.name or self.username


class Team(Base):
    """Who works a shift: one person, or the people who cover it together. Every rota
    row, rotation position, pattern day and change request names a team."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    calendar_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped[User | None] = relationship(back_populates="teams")

    @property
    def can_login(self) -> bool:
        """Whether anyone signs in for this team."""
        return self.user is not None

    @property
    def is_admin(self) -> bool:
        """Administrator rights belong to the user, so every team it covers has them."""
        return bool(self.user and self.user.is_admin)

    @property
    def username(self) -> str | None:
        return self.user.username if self.user else None


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


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("schedule_id", "date", name="uq_assignment_schedule_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="generated", nullable=False)  # generated | manual | swap
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    schedule: Mapped[Schedule] = relationship()
    team: Mapped[Team | None] = relationship()


class SwapRequest(Base):
    """A swap is one shift for one shift: `assignment_id` goes to the target and
    `target_assignment_id` comes back to the requester."""

    __tablename__ = "swap_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    target_assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assignments.id", ondelete="SET NULL"), nullable=True
    )
    requester_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    target_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    accepted_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    assignment: Mapped[Assignment] = relationship(foreign_keys=[assignment_id])
    target_assignment: Mapped[Assignment | None] = relationship(foreign_keys=[target_assignment_id])
    requester: Mapped[Team] = relationship(foreign_keys=[requester_id])
    target_team: Mapped[Team | None] = relationship(foreign_keys=[target_team_id])
    accepted_by: Mapped[Team | None] = relationship(foreign_keys=[accepted_team_id])


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="email", nullable=False)
    recipient: Mapped[str | None] = mapped_column(String(254), nullable=True)
    subject: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # sent | skipped | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    team: Mapped[Team | None] = relationship()
