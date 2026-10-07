from fastapi import APIRouter, Depends, Request
from sqlalchemy import func

from ...models import DisplaySettings as DisplayRow
from ...schemas.settings import DisplayInput
from ...services.state import get_display
from ..dependencies import DB, changed, require_admin

router = APIRouter(prefix="/api/admin/display", dependencies=[Depends(require_admin)])


@router.get("")
@router.head("", include_in_schema=False)
def read_display(db: DB):
    return get_display(db)


@router.put("")
def update_display(body: DisplayInput, db: DB, request: Request):
    row = db.get(DisplayRow, 1)
    row.active_panel, row.zoom_percent, row.updated_at = body.active_panel, body.zoom_percent, func.current_timestamp()
    changed(db, request)
    return get_display(db)
