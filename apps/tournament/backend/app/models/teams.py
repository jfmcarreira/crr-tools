from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Group(Base):
    __tablename__ = "league_groups"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0"), CheckConstraint("sort_order >= 0"),
                      {"sqlite_autoincrement": True})
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text(collation="NOCASE"), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, unique=True)
    created_at: Mapped[str] = mapped_column(Text, default=func.current_timestamp())
    updated_at: Mapped[str] = mapped_column(Text, default=func.current_timestamp())


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (CheckConstraint("number > 0"), CheckConstraint("length(trim(name)) > 0"),
                      Index("idx_teams_group", "group_id"), {"sqlite_autoincrement": True})
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(Text)
    group_id: Mapped[int] = mapped_column(ForeignKey("league_groups.id"))
    created_at: Mapped[str] = mapped_column(Text, default=func.current_timestamp())
    updated_at: Mapped[str] = mapped_column(Text, default=func.current_timestamp())


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0"), CheckConstraint("sort_order >= 0"),
                      Index("idx_players_team_order", "team_id", "sort_order"), {"sqlite_autoincrement": True})
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer)
