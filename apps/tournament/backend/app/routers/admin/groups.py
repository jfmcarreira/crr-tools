from fastapi import APIRouter, Depends, Request

from ...schemas.base import PositiveId
from ...schemas.teams import NameInput
from ...services import teams
from ...services.state import get_groups
from ..dependencies import DB, changed, require_admin

router = APIRouter(prefix="/api/admin/groups", dependencies=[Depends(require_admin)])


@router.get("")
@router.head("", include_in_schema=False)
def read_groups(db: DB):
    return get_groups(db)


@router.post("", status_code=201)
def create_group(body: NameInput, db: DB, request: Request):
    result = teams.create_group(db, body.name)
    changed(db, request)
    return result


@router.put("/{id}")
def update_group(id: PositiveId, body: NameInput, db: DB, request: Request):
    result = teams.update_group(db, id, body.name)
    changed(db, request)
    return result


@router.delete("/{id}")
def delete_group(id: PositiveId, db: DB, request: Request):
    teams.delete_group(db, id)
    changed(db, request)
    return {"ok": True}
