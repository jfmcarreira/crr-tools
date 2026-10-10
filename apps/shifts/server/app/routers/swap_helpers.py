from __future__ import annotations

from datetime import date
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Assignment, Schedule, SwapRequest, Team, User
from ..services.scheduling import in_scheduling_window, scheduling_horizon
from .dependencies import _beyond_horizon_message, _user_teams
from .schedule_helpers import _schedule_team_ids

def _active_request(db: Session, assignment_id: int) -> int | None:
    return db.scalar(
        select(SwapRequest.id).where(
            SwapRequest.assignment_id == assignment_id,
            SwapRequest.status.in_(["open", "pending_approval"]),
        )
    )


def _swap_side(
    db: Session, schedule: Schedule, assignment_id: int | None, *, exclude_team_id: int | None = None
) -> Assignment:
    """One side of a swap: an assigned, future shift of the same schedule."""
    assignment = db.get(Assignment, assignment_id) if assignment_id else None
    if not assignment:
        raise HTTPException(status_code=400, detail="Escolha o turno da outra equipa")
    if assignment.schedule_id != schedule.id:
        raise HTTPException(status_code=400, detail="Só pode trocar com quem trabalha nesta escala")
    if assignment.team_id is None or assignment.team_id == exclude_team_id:
        raise HTTPException(status_code=400, detail="Escolha o turno de outra equipa")
    if assignment.date < date.today():
        raise HTTPException(status_code=400, detail="Turnos passados não podem ser alterados")
    if assignment.date > scheduling_horizon():
        raise HTTPException(status_code=400, detail=_beyond_horizon_message())
    if _active_request(db, assignment.id):
        raise HTTPException(status_code=400, detail="Esse turno já tem um pedido de troca")
    return assignment


def _swap_partner(db: Session, schedule: Schedule, team_id: int | None) -> Team:
    """The one team this swap is with: active and working the same schedule."""
    if not team_id:
        raise HTTPException(status_code=400, detail="Escolha a equipa que fica com o turno")
    if team_id not in _schedule_team_ids(db, schedule.id):
        raise HTTPException(
            status_code=400, detail="Só pode trocar com quem trabalha nesta escala"
        )
    partner = db.get(Team, team_id)
    if not partner or not partner.is_active:
        raise HTTPException(status_code=400, detail="Equipa inválida para este turno")
    return partner


def _reject_swap(db: Session, swap: SwapRequest) -> None:
    swap.status = "rejected"
    db.commit()


def _rejectable(user: User, my_ids: set[int], swap: SwapRequest) -> bool:
    """Anyone eligible may decline an open request; admins can also drop a pending one."""
    if user.is_admin:
        return True
    if swap.status != "open" or swap.requester_id in my_ids:
        return False
    return swap.target_team_id is None or swap.target_team_id in my_ids


def _swap_ownership_holds(db: Session, swap: SwapRequest) -> bool:
    """Both teams must still own their own shift, otherwise the swap is void."""
    if swap.assignment.team_id != swap.requester_id:
        return False
    if swap.target_assignment_id is not None and swap.target_assignment is not None:
        if swap.target_assignment.team_id != swap.target_team_id:
            return False
    return True


def _complete_swap(db: Session, swap: SwapRequest, new_team: Team) -> None:
    """Exchange both shifts and close the request. Ownership must be checked by the caller."""
    for side in (swap.assignment, swap.target_assignment):
        if side is not None and not in_scheduling_window(side.date):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Turnos passados não podem ser alterados"
                    if side.date < date.today()
                    else _beyond_horizon_message()
                ),
            )
    swap.assignment.team_id = new_team.id
    swap.assignment.source = "swap"
    incoming = swap.target_assignment
    if incoming is not None:
        incoming.team_id = swap.requester_id
        incoming.source = "swap"
    swap.accepted_team_id = new_team.id
    swap.status = "approved"
    for other in db.scalars(
        select(SwapRequest).where(
            SwapRequest.id != swap.id,
            SwapRequest.status.in_(["open", "pending_approval"]),
            (
                (SwapRequest.assignment_id == swap.assignment_id)
                | (SwapRequest.target_assignment_id == swap.assignment_id)
                | (
                    (SwapRequest.assignment_id.is_not(None))
                    & (SwapRequest.assignment_id == swap.target_assignment_id)
                )
                | (
                    (SwapRequest.target_assignment_id.is_not(None))
                    & (SwapRequest.target_assignment_id == swap.target_assignment_id)
                )
            ),
        )
    ).all():
        other.status = "cancelled"
    db.commit()


def _accepting_team(db: Session, user: User, swap: SwapRequest) -> Team:
    """Which team takes the shift: the one it was asked of, or the first active one
    assigned to this user. The user answers as a whole; the rota records one team."""
    if swap.target_team_id:
        target = db.get(Team, swap.target_team_id)
        if target is not None and target.user_id == user.id and target.is_active:
            return target
    for team in _user_teams(db, user):
        if team.is_active:
            return team
    raise HTTPException(status_code=400, detail="Este utilizador não tem nenhuma equipa ativa para o turno")
