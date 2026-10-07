from sqlalchemy import CheckConstraint, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TournamentSettings(Base):
    __tablename__ = "tournament_settings"
    __table_args__ = (
        CheckConstraint("id = 1"), CheckConstraint("length(trim(name)) > 0"),
        CheckConstraint("final_round_count IS NULL OR (final_round_count BETWEEN 1 AND 8)"),
        CheckConstraint("third_place_enabled IN (0, 1)"),
        CheckConstraint("classification_mode IN ('standard', 'total-points')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    final_round_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(Text, default=func.current_timestamp())
    updated_at: Mapped[str] = mapped_column(Text, default=func.current_timestamp())
    third_place_enabled: Mapped[int] = mapped_column(Integer, server_default="0")
    classification_mode: Mapped[str] = mapped_column(Text, server_default="standard")


class DisplaySettings(Base):
    __tablename__ = "display_settings"
    __table_args__ = (
        CheckConstraint("id = 1"), CheckConstraint("length(trim(active_panel)) > 0"),
        CheckConstraint("zoom_percent BETWEEN 50 AND 400"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active_panel: Mapped[str] = mapped_column(Text)
    zoom_percent: Mapped[int] = mapped_column(Integer, server_default="100")
    created_at: Mapped[str] = mapped_column(Text, default=func.current_timestamp())
    updated_at: Mapped[str] = mapped_column(Text, default=func.current_timestamp())
