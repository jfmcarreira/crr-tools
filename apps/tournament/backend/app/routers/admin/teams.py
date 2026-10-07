from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from ...models import Player
from ...errors import AppError
from ...schemas.base import Confirmation, PositiveId
from ...schemas.teams import NameInput, TeamCreate, TeamInput
from ...services import teams
from ...services.state import get_admin_teams, player_from_row
from ..dependencies import DB, changed, confirm, require_admin

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


@router.get("/teams")
@router.head("/teams", include_in_schema=False)
def read_teams(db: DB):
    return get_admin_teams(db)


@router.post("/teams/randomize")
def randomize(db: DB, request: Request, body: Confirmation | None = None):
    confirm(body is not None and body.confirm, "Confirme que pretende randomizar os números e os grupos das equipas.")
    result = teams.randomize_teams(db)
    changed(db, request)
    return result


@router.post("/teams", status_code=201)
def create_team(body: TeamCreate, db: DB, request: Request):
    result = teams.create_team(db, body)
    changed(db, request)
    return result


@router.put("/teams/{id}")
def update_team(id: PositiveId, body: TeamInput, db: DB, request: Request):
    result = teams.update_team(db, id, body)
    changed(db, request)
    return result


@router.delete("/teams/{id}")
def delete_team(id: PositiveId, db: DB, request: Request):
    teams.delete_team(db, id)
    changed(db, request)
    return {"ok": True}


@router.post("/teams/{teamId}/players", status_code=201)
def create_player(teamId: PositiveId, body: NameInput, db: DB, request: Request):
    teams.existing_team(db, teamId)
    order = db.scalar(select(func.max(Player.sort_order)).where(Player.team_id == teamId))
    row = Player(team_id=teamId, name=body.name, sort_order=0 if order is None else order + 1)
    db.add(row)
    db.flush()
    result = player_from_row(row)
    changed(db, request)
    return result


def existing_player(db, identifier):
    row = db.get(Player, identifier)
    if row is None:
        raise AppError(404, "O jogador não existe.")
    return row


@router.put("/players/{id}")
def update_player(id: PositiveId, body: NameInput, db: DB, request: Request):
    row = existing_player(db, id)
    row.name = body.name
    result = player_from_row(row)
    changed(db, request)
    return result


@router.delete("/players/{id}")
def delete_player(id: PositiveId, db: DB, request: Request):
    db.delete(existing_player(db, id))
    changed(db, request)
    return {"ok": True}
