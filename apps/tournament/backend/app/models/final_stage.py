from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FinalSeed(Base):
    __tablename__ = "final_seeds"
    __table_args__ = (CheckConstraint("slot_index >= 1"),
                      Index("idx_final_seeds_unique_team", "team_id", unique=True, sqlite_where=text("team_id IS NOT NULL")))
    slot_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))


class FinalResult(Base):
    __tablename__ = "final_match_results"
    __table_args__ = (
        CheckConstraint("round_index >= 1"), CheckConstraint("match_index >= 1"),
        CheckConstraint("(score_a IS NULL AND score_b IS NULL) OR (score_a IS NOT NULL AND score_b IS NOT NULL AND score_a >= 0 AND score_b >= 0)"),
    )
    round_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    score_a: Mapped[int | None] = mapped_column(Integer)
    score_b: Mapped[int | None] = mapped_column(Integer)
