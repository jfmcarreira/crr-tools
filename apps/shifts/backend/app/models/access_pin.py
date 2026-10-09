from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class AccessPin(Base):
    __tablename__ = "access_pins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("assignments.id", ondelete="SET NULL"), nullable=True)
    lock_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    keyboard_pwd_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    encrypted_pin: Mapped[str | None] = mapped_column(String(512), nullable=True)
    valid_from_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_until_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    request_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False,
    )
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )

    user = relationship("User")
    team = relationship("Team")
    assignment = relationship("Assignment")
