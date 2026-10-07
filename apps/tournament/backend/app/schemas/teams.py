from pydantic import Field, field_validator

from .base import Name, PositiveId, PositiveInt, RequestSchema, Schema


class Group(Schema):
    id: int
    name: str
    sort_order: int


class TeamSummary(Schema):
    id: int
    number: int
    name: str
    group: Group


class Player(Schema):
    id: int
    team_id: int
    name: str
    sort_order: int


class Team(TeamSummary):
    players: list[Player] = Field(default_factory=list)


class NameInput(RequestSchema):
    name: Name


class TeamInput(NameInput):
    number: PositiveInt
    group_id: PositiveId


class TeamCreate(NameInput):
    number: PositiveInt | None = None
    group_id: PositiveId

    @field_validator("number", mode="before")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("number must be omitted or positive")
        return value
