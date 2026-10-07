from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from ...models import LeagueMatch
from ...schemas.base import Confirmation
from ...schemas.calendar import GenerationInput, PreviewInput
from ...services import calendar_store
from ...services.state import get_matches
from ..dependencies import DB, changed, confirm, require_admin

router = APIRouter(prefix="/api/admin/calendar", dependencies=[Depends(require_admin)])


@router.get("")
@router.head("", include_in_schema=False)
def read_calendar(db: DB):
    return calendar_store.summary(get_matches(db))


@router.post("/generate-preview")
def preview(body: PreviewInput, db: DB):
    return calendar_store.generate_preview(db, body.legs)


@router.post("/generate")
def generate(body: GenerationInput, db: DB, request: Request):
    result = calendar_store.save_calendar(db, body)
    changed(db, request)
    return result


@router.delete("")
def clear(db: DB, request: Request, body: Confirmation | None = None):
    if db.scalar(select(LeagueMatch.id).limit(1)) is not None:
        confirm(body is not None and body.confirm, "Confirme que pretende limpar o calendário e todos os seus resultados.")
        calendar_store.clear_calendar(db)
        changed(db, request)
    return {"ok": True}
