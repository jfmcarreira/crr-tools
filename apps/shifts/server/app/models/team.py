from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .user import User

class Team(Base):
    """Who works a shift: one person, or the people who cover it together. Every rota
    row, rotation position, pattern day and change request names a team. Notifications
    and the address they go to belong to the user who signs in for it, not to the team."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    calendar_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
