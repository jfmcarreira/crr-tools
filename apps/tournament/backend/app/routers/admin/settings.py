from fastapi import APIRouter, Depends, Request
from sqlalchemy import func

from ...models import TournamentSettings
from ...schemas.settings import SettingsInput
from ...services.state import get_settings
from ..dependencies import DB, changed, require_admin

router = APIRouter(prefix="/api/admin/settings", dependencies=[Depends(require_admin)])


@router.get("")
@router.head("", include_in_schema=False)
def read_settings(db: DB):
    return get_settings(db)


@router.put("")
def update_settings(body: SettingsInput, db: DB, request: Request):
    row = db.get(TournamentSettings, 1)
    row.name, row.classification_mode, row.updated_at = body.name, body.classification_mode, func.current_timestamp()
    changed(db, request)
    return get_settings(db)
