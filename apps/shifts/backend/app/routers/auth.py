from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..security import verify_password
from .dependencies import _check_csrf, _context, _current_user, _flash, _redirect, _user_label, _user_teams

router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if _current_user(request, db):
        return _redirect("/")
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="login.html",
        context=_context(request, db),
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    user = db.scalar(
        select(User).where(func.lower(User.username) == username.strip().lower())
    )
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        _flash(request, "Nome de utilizador ou palavra-passe inválidos.", "error")
        return _redirect("/login")
    request.session["user_id"] = user.id
    teams = _user_teams(db, user)
    who = ", ".join(team.name for team in teams) or _user_label(user)
    _flash(request, f"Bem-vindo(a), {who}.")
    return _redirect("/")


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    _check_csrf(request, csrf_token)
    request.session.clear()
    return _redirect("/login")
