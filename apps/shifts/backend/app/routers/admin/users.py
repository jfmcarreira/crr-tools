from __future__ import annotations

from collections.abc import Sequence
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from ...database import get_db
from ...models import NotificationLog, Team, User
from ...security import hash_password
from .user_helpers import _usable_admin_users
from ..dependencies import _check_csrf, _context, _flash, _redirect, _require_admin

router = APIRouter()

@router.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, db: Session = Depends(get_db)):
    """The users: created here, then assigned to the teams they sign in for."""
    admin = _require_admin(request, db)
    users = db.scalars(
        select(User).options(selectinload(User.teams)).order_by(User.username)
    ).all()
    removable_ids = {user.id for user in users if _user_removal_blocker(db, admin, user) is None}
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin_users.html",
        context=_context(
            request,
            db,
            users=users,
            removable_ids=removable_ids,
            teams=db.scalars(select(Team).order_by(Team.name)).all(),
        ),
    )


def _user_removal_blocker(db: Session, admin: User, user: User) -> str | None:
    """Why this user cannot be removed, or None when the removal is allowed."""
    teams = db.scalars(select(Team).where(Team.user_id == user.id).order_by(Team.name)).all()
    if teams:
        return f"Está atribuído a {len(teams)} equipa(s)"
    if user.id == admin.id:
        return "Não pode remover o seu próprio acesso"
    if user.is_admin and not _usable_admin_users(db, exclude=user):
        return "Não pode remover o último administrador"
    return None


@router.post("/admin/users")
def admin_create_user(
    request: Request,
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    email: str = Form(""),
    team_ids: list[str] = Form([]),
    is_admin: str = Form(""),
    notify_email: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """A new user, assigned to the teams it will sign in for."""
    _check_csrf(request, csrf_token)
    _require_admin(request, db)
    user, error = _new_user(
        db, name, username, password, email=email, is_admin=bool(is_admin),
        notify_email=bool(notify_email),
    )
    if error:
        _flash(request, error, "error")
        return _redirect("/admin/users")
    db.add(user)
    db.commit()
    _assign_user_to_teams(db, user, team_ids)
    db.commit()
    _flash(request, "Utilizador criado.")
    return _redirect("/admin/users")


def _new_user(
    db: Session, name: str, username: str, password: str, *, email: str = "",
    is_admin: bool, notify_email: bool = True,
) -> tuple[User | None, str | None]:
    """A user with a username and a password, unsaved, or the reason it was refused."""
    value = username.strip().lower()
    if not value:
        return None, "Defina um nome de utilizador."
    if db.scalar(select(User.id).where(User.username == value)):
        return None, "Esse nome de utilizador já existe."
    email_value = email.strip().lower() or None
    if email_value and db.scalar(select(User.id).where(User.email == email_value)):
        return None, "Esse endereço de e-mail já existe."
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        return None, str(exc)
    return (
        User(
            name=name.strip() or value,
            username=value,
            password_hash=password_hash,
            email=email_value,
            is_admin=is_admin,
            is_active=True,
            notify_email=notify_email,
        ),
        None,
    )


def _assign_user_to_teams(db: Session, user: User, team_ids: Sequence[str]) -> None:
    """Attach this user to exactly the teams the form selected."""
    chosen = {int(value) for value in team_ids if str(value).isdigit()}
    for team in db.scalars(select(Team)).all():
        if (team.id in chosen) != (team.user_id == user.id):
            team.user = user if team.id in chosen else None


@router.post("/admin/users/{user_id}/update")
def admin_update_user(
    user_id: int,
    request: Request,
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(""),
    email: str = Form(""),
    team_ids: list[str] = Form([]),
    is_admin: str = Form(""),
    is_active: str = Form(""),
    notify_email: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    admin = _require_admin(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    username_value = username.strip().lower()
    if not username_value:
        _flash(request, "O nome de utilizador não pode ficar vazio.", "error")
        return _redirect("/admin/users")
    duplicate = db.scalar(
        select(User.id).where(User.username == username_value, User.id != user.id)
    )
    if duplicate:
        _flash(request, "Esse nome de utilizador já está a ser usado.", "error")
        return _redirect("/admin/users")
    email_value = email.strip().lower() or None
    email_taken = (
        db.scalar(select(User.id).where(User.email == email_value, User.id != user.id))
        if email_value
        else None
    )
    if email_taken:
        _flash(request, "Esse endereço de e-mail já está a ser usado.", "error")
        return _redirect("/admin/users")
    loses_admin = user.is_admin and not is_admin
    loses_access = user.id == admin.id and not is_active
    last_admin = loses_admin and not _usable_admin_users(db, exclude=user)
    if last_admin:
        _flash(request, "Não pode tirar a administração ao último utilizador que a tem.", "error")
        return _redirect("/admin/users")
    if loses_access:
        _flash(request, "Não pode desativar o acesso com que está ligado.", "error")
        return _redirect("/admin/users")
    if password.strip():
        try:
            user.password_hash = hash_password(password.strip())
        except ValueError as exc:
            _flash(request, str(exc), "error")
            return _redirect("/admin/users")

    user.name = name.strip() or username_value
    user.username = username_value
    user.email = email_value
    user.is_admin = bool(is_admin)
    user.is_active = True if user.id == admin.id else bool(is_active)
    user.notify_email = bool(notify_email)
    db.commit()
    _assign_user_to_teams(db, user, team_ids)
    db.commit()
    _flash(request, "Utilizador atualizado.")
    return _redirect("/admin/users")


@router.post("/admin/users/{user_id}/delete")
def admin_user_delete(
    user_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    admin = _require_admin(request, db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    reason = _user_removal_blocker(db, admin, user)
    if reason:
        _flash(request, f"Não é possível remover este utilizador: {reason}.", "error")
        return _redirect("/admin/users")
    # SQLite cascades are not enforced by the application, exactly as on team removal:
    # the e-mail history stays, without the user it was addressed to.
    for log in db.scalars(select(NotificationLog).where(NotificationLog.user_id == user.id)).all():
        log.user_id = None
    db.delete(user)
    db.commit()
    _flash(request, "Utilizador removido.")
    return _redirect("/admin/users")
