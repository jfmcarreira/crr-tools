from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from .base import Confirmed, PositiveId, RequestSchema, Schema, Score, number
from .teams import Group, TeamSummary

Legs = Annotated[Literal[1, 2], BeforeValidator(number)]


class GenerationTeam(RequestSchema):
    team_id: PositiveId
    group_id: PositiveId


class Generation(RequestSchema):
    legs: Legs
    team_order: list[GenerationTeam]


class GenerationInput(RequestSchema):
    generation: Generation
    confirm_replace: Confirmed = False


class PreviewInput(RequestSchema):
    legs: Legs


class CalendarMatch(Schema):
    game_number: int
    round_number: int
    group: Group | None
    team_a: TeamSummary
    team_b: TeamSummary


class LeagueMatch(CalendarMatch):
    id: int
    counts_toward_standings: bool
    score_a: int | None
    score_b: int | None


class ResultInput(RequestSchema):
    score_a: Score
    score_b: Score


class StandingsInput(RequestSchema):
    counts_toward_standings: Annotated[bool, Field(strict=True)]
