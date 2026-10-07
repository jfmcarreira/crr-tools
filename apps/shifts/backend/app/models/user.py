from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .team import Team

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
