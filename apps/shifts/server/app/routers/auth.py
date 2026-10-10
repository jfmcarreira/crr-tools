from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
import re

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..database import get_db
from ..config import settings
from ..models import Team, User
from ..security import hash_password, verify_password
from .dependencies import _check_csrf, _context, _current_user, _flash, _redirect, _user_label, _user_teams

router = APIRouter()


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    if not settings.registration_enabled or _current_user(request, db):
        return _redirect("/")
    team_name = request.query_params.get("team_name", "")
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="register.html",
        context={**_context(request, db), "step": "team", "team_name": team_name},
    )


@router.post("/register")
def register(
    request: Request,
    step: str = Form("team"),
    team_name: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if not settings.registration_enabled or request.session.get("user_id"):
        return _redirect("/")
    _check_csrf(request, csrf_token)

    if step == "team":
        team_name_clean = team_name.strip()
        if not team_name_clean:
            _flash(request, "Indique o nome da sua equipa.", "error")
            return _redirect("/register")
        matches = [
            team for team in db.scalars(select(Team)).all()
            if team.name.strip().casefold() == team_name_clean.casefold()
        ]
        if len(matches) != 1 or not matches[0].is_active or matches[0].user_id is not None:
            _flash(request, "Equipa não encontrada ou indisponível para registo.", "error")
            return _redirect("/register")
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="register.html",
            context={**_context(request, db), "step": "user", "team_name": matches[0].name},
        )

    if step != "user":
        return _redirect("/register")

    host = request.client.host if request.client else ""
    if not request.app.state.registration_limiter.consume(host):
        _flash(request, "Demasiadas tentativas de registo. Tente novamente mais tarde.", "error")
        return _redirect("/register")
    team_name_clean = team_name.strip()
    matches = [
        team for team in db.scalars(select(Team)).all()
        if team.name.strip().casefold() == team_name_clean.casefold()
    ]
    if len(matches) != 1 or not matches[0].is_active or matches[0].user_id is not None:
        _flash(request, "Equipa não encontrada ou indisponível para registo.", "error")
        return _redirect("/register")
    team = matches[0]

    # Username is provided by user (name copied from team)
    value = username.strip().lower()

    error = None
    if not re.fullmatch(r"[a-z0-9._-]{1,80}", value):
        error = "Defina um nome de utilizador válido (letras, números, ponto, traço ou sublinhado)."
    elif db.scalar(select(User.id).where(func.lower(User.username) == value)):
        error = "Esse nome de utilizador já existe."
    if error:
        _flash(request, error, "error")
        return _redirect("/register")

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        _flash(request, str(exc), "error")
        return _redirect("/register")

    user = User(
        name=team.name,
        username=value,
        password_hash=password_hash,
        is_admin=False,
        is_active=True,
        can_request_pin=False,
    )
    try:
        db.add(user)
        db.flush()
        claimed = db.execute(
            update(Team).where(
                Team.id == team.id, Team.user_id.is_(None), Team.is_active.is_(True),
            ).values(user_id=user.id)
        )
        if claimed.rowcount != 1:
            db.rollback()
            _flash(request, "Equipa não encontrada ou indisponível para registo.", "error")
            return _redirect("/register")
        db.commit()
    except IntegrityError:
        db.rollback()
        _flash(request, "Não foi possível criar a conta. Tente novamente.", "error")
        return _redirect("/register")
    request.session.clear()
    request.session["user_id"] = user.id
    _flash(request, "Conta criada com sucesso.")
    return _redirect("/")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if _current_user(request, db):
        return _redirect("/")
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="login.html",
        context=_context(request, db),
    )


def _rate_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else ""
    return f"{host}:{username.strip().lower()}"


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    limiter = request.app.state.limiter
    key = _rate_key(request, username)
    if limiter.limited(key):
        _flash(
            request,
            "Demasiadas tentativas de início de sessão. Tente novamente mais tarde.",
            "error",
        )
        return _redirect("/login")
    user = db.scalar(
        select(User).where(func.lower(User.username) == username.strip().lower())
    )
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        limiter.failure(key)
        _flash(request, "Nome de utilizador ou palavra-passe inválidos.", "error")
        return _redirect("/login")
    limiter.clear(key)
    request.session["user_id"] = user.id
    teams = _user_teams(db, user)
    who = ", ".join(team.name for team in teams) or _user_label(user)
    return _redirect("/")


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    _check_csrf(request, csrf_token)
    request.session.clear()
    return _redirect("/login")
