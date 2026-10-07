from fastapi import APIRouter, Depends, Request

from ...errors import AppError
from ...models import LeagueMatch, LeagueRound
from ...schemas.base import PositiveId
from ...schemas.calendar import ResultInput, StandingsInput
from ...services.state import get_matches
from ..dependencies import DB, changed, require_admin

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


def existing_match(db, identifier):
    row = db.get(LeagueMatch, identifier)
    if row is None:
        raise AppError(404, "O jogo não existe.")
    return row


@router.put("/matches/{id}/result")
def save_result(id: PositiveId, body: ResultInput, db: DB, request: Request):
    row = existing_match(db, id)
    row.score_a, row.score_b = body.score_a, body.score_b
    changed(db, request)
    return next(match for match in get_matches(db) if match.id == id)


@router.delete("/matches/{id}/result")
def clear_result(id: PositiveId, db: DB, request: Request):
    row = existing_match(db, id)
    row.score_a = row.score_b = None
    changed(db, request)
    return {"ok": True}


@router.put("/rounds/{round}/standings")
def save_standings(round: PositiveId, body: StandingsInput, db: DB, request: Request):
    row = db.get(LeagueRound, round)
    if row is None:
        raise AppError(404, "A jornada não existe.")
    row.counts_toward_standings = int(body.counts_toward_standings)
    changed(db, request)
    return {"roundNumber": round, "countsTowardStandings": body.counts_toward_standings}
