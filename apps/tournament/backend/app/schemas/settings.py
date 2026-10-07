from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field

from .base import Name, RequestSchema, Schema, number

ClassificationMode = Literal["standard", "total-points"]
DisplayPanel = Literal["next-match", "latest-results", "classification"]


class SettingsInput(RequestSchema):
    name: Name
    classification_mode: ClassificationMode


class TournamentSettings(Schema):
    name: str
    classification_mode: ClassificationMode
    final_round_count: int | None
    third_place_enabled: bool


class DisplaySettings(Schema):
    active_panel: DisplayPanel
    zoom_percent: Annotated[int, BeforeValidator(number), Field(ge=50, le=400)]


class DisplayInput(DisplaySettings):
    model_config = ConfigDict(populate_by_name=False, validate_by_name=False, validate_by_alias=True)
