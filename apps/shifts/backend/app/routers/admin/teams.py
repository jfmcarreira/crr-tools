from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload
from ...database import get_db
from ...models import Assignment, MonthlyPattern, NotificationLog, RotationMember, SwapRequest, Team, User
from .user_helpers import _usable_admin_users
from ..dependencies import _check_csrf, _context, _flash, _redirect, _require_admin

router = APIRouter()

@router.get("/admin/teams", response_class=HTMLResponse)
def admin_teams(request: Request, db: Session = Depends(get_db)):
    """Who works the rota. Users are not created here: a team only picks who signs in for it."""
    admin = _require_admin(request, db)
    teams = db.scalars(
        select(Team)
        .options(selectinload(Team.user).selectinload(User.teams))
        .order_by(Team.name)
    ).all()
    removable_ids = {team.id for team in teams if _team_removal_blocker(db, admin, team) is None}
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin_teams.html",
        context=_context(
            request,
            db,
            teams=teams,
            removable_ids=removable_ids,
            users_by_id=_users_by_id(db),
        ),
    )


def _users_by_id(db: Session) -> dict[int, User]:
    return {user.id: user for user in db.scalars(select(User).order_by(User.username)).all()}


@router.post("/admin/teams")
def admin_create_team(
    request: Request,
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    assigned_user_id: str = Form(""),
    notify_email: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """Add a team to the rota. The user who signs in for it is chosen here or later."""
    _check_csrf(request, csrf_token)
    _require_admin(request, db)
    email_value = email.strip().lower() or None
    if email_value and db.scalar(select(Team.id).where(Team.email == email_value)):
        _flash(request, "Esse endereço de e-mail já existe.", "error")
        return _redirect("/admin/teams")
    db.add(
        Team(
            name=name.strip(),
            user=_chosen_user(db, assigned_user_id),
            email=email_value,
            phone=phone.strip() or None,
            is_active=True,
            notify_email=bool(notify_email),
        )
    )
    db.commit()
    _flash(request, "Equipa criada.")
    return _redirect("/admin/teams")


def _chosen_user(db: Session, raw: str) -> User | None:
    """The user picked in a form, or None for "nobody signs in for this team"."""
    value = raw.strip()
    if not value.isdigit():
        return None
    user = db.get(User, int(value))
    if user is None:
        raise HTTPException(status_code=400, detail="Utilizador inválido")
    return user


@router.post("/admin/teams/{team_id}/update")
def admin_update_team(
    team_id: int,
    request: Request,
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    assigned_user_id: str = Form(""),
    is_active: str = Form(""),
    notify_email: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    admin = _require_admin(request, db)
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Equipa não encontrada")
    email_value = email.strip().lower() or None
    duplicate = (
        db.scalar(select(Team.id).where(Team.email == email_value, Team.id != team.id))
        if email_value
        else None
    )
    if duplicate:
        _flash(request, "Esse endereço de e-mail já está a ser usado.", "error")
        return _redirect("/admin/teams")

    # Whoever is signed in must keep an active team to sign in with, not necessarily this one.
    chosen = _chosen_user(db, assigned_user_id)
    stays_active = bool(is_active)
    if _loses_last_team(db, admin, team, chosen, stays_active):
        _flash(request, "Não pode desativar a última equipa do utilizador com que está ligado.", "error")
        return _redirect("/admin/teams")

    team.name = name.strip()
    team.user = chosen
    team.email = email_value
    team.phone = phone.strip() or None
    team.notify_email = bool(notify_email)
    team.is_active = stays_active
    db.commit()
    _flash(request, "Equipa atualizada.")
    return _redirect("/admin/teams")


def _loses_last_team(
    db: Session, user: User, team: Team, chosen: User | None, stays_active: bool
) -> bool:
    """True when this edit would leave the user without any active team to sign in with."""
    still_mine = chosen is not None and chosen.id == user.id and stays_active
    if still_mine:
        return False
    return not db.scalar(
        select(Team.id).where(
            Team.user_id == user.id, Team.id != team.id, Team.is_active.is_(True)
        )
    )


def _team_removal_impact(db: Session, team: Team) -> dict[str, int]:
    return {
        "assignments": db.scalar(
            select(func.count(Assignment.id)).where(Assignment.team_id == team.id)
        ) or 0,  # must be zero for the removal to be allowed
        "rotation": db.scalar(
            select(func.count(RotationMember.id)).where(RotationMember.team_id == team.id)
        ) or 0,
        "pattern_days": db.scalar(
            select(func.count(MonthlyPattern.id)).where(MonthlyPattern.team_id == team.id)
        ) or 0,
        "requests": db.scalar(
            select(func.count(SwapRequest.id)).where(
                SwapRequest.status.in_(["open", "pending_approval"]),
                (
                    (SwapRequest.requester_id == team.id)
                    | (SwapRequest.target_team_id == team.id)
                    | (SwapRequest.accepted_team_id == team.id)
                ),
            )
        ) or 0,
    }


def _team_removal_blocker(db: Session, admin: User, team: Team) -> str | None:
    """Why this team cannot be removed, or None when the removal is allowed."""
    user = team.user
    if user is not None and user.id == admin.id and not db.scalar(
        select(Team.id).where(Team.user_id == user.id, Team.id != team.id)
    ):
        return "Não pode remover a si próprio(a)"
    if user is not None and user.is_admin and not _usable_admin_users(db, exclude=user):
        return "Não pode remover a equipa do último administrador"
    if db.scalar(select(Assignment.id).where(Assignment.team_id == team.id)):
        return "Não pode remover uma equipa que ainda tem turnos atribuídos"
    return None


def _require_removable(db: Session, admin: User, team: Team) -> None:
    reason = _team_removal_blocker(db, admin, team)
    if reason:
        raise HTTPException(status_code=400, detail=reason)


@router.get("/admin/teams/{team_id}/delete", response_class=HTMLResponse)
def admin_team_delete_page(
    team_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Equipa não encontrada")
    _require_removable(db, admin, team)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin_team_delete.html",
        context=_context(request, db, team=team, impact=_team_removal_impact(db, team)),
    )


@router.post("/admin/teams/{team_id}/delete")
def admin_team_delete(
    team_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    _check_csrf(request, csrf_token)
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Equipa não encontrada")
    _require_removable(db, admin, team)

    # No assignment can survive here: _require_removable refuses while the team holds one.
    for swap in db.scalars(
        select(SwapRequest).where(SwapRequest.requester_id == team.id)
    ).all():
        db.delete(swap)
    for swap in db.scalars(
        select(SwapRequest).where(
            (SwapRequest.target_team_id == team.id) | (SwapRequest.accepted_team_id == team.id)
        )
    ).all():
        if swap.target_team_id == team.id:
            swap.target_team_id = None
        if swap.accepted_team_id == team.id:
            swap.accepted_team_id = None
    for pattern in db.scalars(
        select(MonthlyPattern).where(MonthlyPattern.team_id == team.id)
    ).all():
        pattern.team_id = None
    for log in db.scalars(
        select(NotificationLog).where(NotificationLog.team_id == team.id)
    ).all():
        log.team_id = None
    db.execute(delete(RotationMember).where(RotationMember.team_id == team.id))
    db.delete(team)
    db.commit()
    return _redirect("/admin/teams")
