from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LeagueMatch(Base):
    __tablename__ = "league_matches"
    __table_args__ = (
        CheckConstraint("order_index >= 1"), CheckConstraint("round_index >= 1"),
        CheckConstraint("team_a_id <> team_b_id"),
        CheckConstraint("(score_a IS NULL AND score_b IS NULL) OR (score_a IS NOT NULL AND score_b IS NOT NULL AND score_a >= 0 AND score_b >= 0)"),
        Index("idx_league_matches_order", "order_index"), {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_index: Mapped[int] = mapped_column(Integer, unique=True)
    round_index: Mapped[int] = mapped_column(Integer)
    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    score_a: Mapped[int | None] = mapped_column(Integer)
    score_b: Mapped[int | None] = mapped_column(Integer)


class LeagueRound(Base):
    __tablename__ = "league_rounds"
    __table_args__ = (CheckConstraint("round_index >= 1"), CheckConstraint("counts_toward_standings IN (0, 1)"))
    round_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    counts_toward_standings: Mapped[int] = mapped_column(Integer, server_default="0")
