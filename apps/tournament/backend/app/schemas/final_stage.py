from typing import Annotated, Literal

from pydantic import Field

from .base import Confirmed, PositiveInt, RequestSchema, Schema
from .teams import TeamSummary


class Participant(Schema):
    team: TeamSummary | None
    pending: bool = False


class BracketMatch(Schema):
    match_index: int
    team_a: Participant
    team_b: Participant
    score_a: int | None = None
    score_b: int | None = None
    winner: TeamSummary | None = None
    is_bye: bool = False


class BracketRound(Schema):
    round_index: int
    name: str
    matches: list[BracketMatch]


class FinalStage(Schema):
    round_count: int | None
    third_place_enabled: bool = False
    rounds: list[BracketRound] = Field(default_factory=list)
    third_place_match: BracketMatch | None = None
    champion: TeamSummary | None = None


class ConfigInput(RequestSchema):
    round_count: Annotated[PositiveInt, Field(le=8)]
    third_place_enabled: Annotated[bool, Field(strict=True)] = False
    confirm_clear_results: Confirmed = False


class Seed(Schema):
    slot_index: PositiveInt
    team_id: PositiveInt | None


class SeedInput(Seed, RequestSchema):
    pass


class SeedsInput(RequestSchema):
    seeds: list[SeedInput]
    confirm_clear_results: Confirmed = False


class PerGroupInput(RequestSchema):
    mode: Literal["per-group"]
    qualifiers_per_group: PositiveInt


class OverallInput(RequestSchema):
    mode: Literal["overall"]
    qualifier_count: PositiveInt


class QualifiedTeam(Schema):
    seed_number: int
    group_position: int
    team: TeamSummary


class SeedPreview(Schema):
    mode: Literal["per-group", "overall"]
    qualifiers_per_group: int | None
    qualifier_count: int
    qualifiers: list[QualifiedTeam]
    seeds: list[Seed]
