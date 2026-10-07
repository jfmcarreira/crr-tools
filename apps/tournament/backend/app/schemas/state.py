from .base import Schema
from .calendar import LeagueMatch
from .final_stage import FinalStage
from .settings import DisplaySettings, TournamentSettings
from .teams import Group, TeamSummary


class ClassificationRow(Schema):
    position: int = 0
    team: TeamSummary
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0
    points: int = 0


class GroupStanding(Schema):
    group: Group
    rows: list[ClassificationRow]


class PublicState(Schema):
    tournament: TournamentSettings
    display: DisplaySettings
    groups: list[Group]
    matches: list[LeagueMatch]
    group_standings: list[GroupStanding]
    final_stage: FinalStage
