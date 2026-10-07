from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request

from ...schemas.base import Confirmation, PositiveId
from ...schemas.calendar import ResultInput
from ...schemas.final_stage import ConfigInput, OverallInput, PerGroupInput, SeedsInput
from ...services import final_stage
from ...services.state import get_final_stage, get_settings
from ..dependencies import DB, changed, confirm, require_admin

router = APIRouter(prefix="/api/admin/final-stage", dependencies=[Depends(require_admin)])


@router.get("")
@router.head("", include_in_schema=False)
def read_stage(db: DB):
    return get_final_stage(db)


@router.put("/config")
def configure(body: ConfigInput, db: DB, request: Request):
    if final_stage.configure(db, body):
        changed(db, request)
    return get_final_stage(db)


@router.delete("/config")
def clear_config(db: DB, request: Request, body: Confirmation | None = None):
    if get_settings(db).final_round_count is not None:
        confirm(body is not None and body.confirm, "Confirme que pretende limpar a configuração e todos os resultados da fase final.")
        final_stage.clear(db)
        changed(db, request)
    return get_final_stage(db)


@router.post("/auto-seed-preview")
def preview(body: Annotated[PerGroupInput | OverallInput, Body(discriminator="mode")], db: DB):
    return final_stage.seed_preview(db, body)


@router.put("/seeds")
def seeds(body: SeedsInput, db: DB, request: Request):
    if final_stage.save_seeds(db, body):
        changed(db, request)
    return get_final_stage(db)


@router.put("/matches/{round}/{match}/result")
def save_result(round: PositiveId, match: PositiveId, body: ResultInput, db: DB, request: Request):
    final_stage.save_result(db, round, match, body.score_a, body.score_b)
    changed(db, request)
    return get_final_stage(db)


@router.delete("/matches/{round}/{match}/result")
def clear_result(round: PositiveId, match: PositiveId, db: DB, request: Request):
    final_stage.clear_result(db, round, match)
    changed(db, request)
    return get_final_stage(db)
