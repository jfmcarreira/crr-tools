from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .assignment import Assignment
    from .team import Team

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
