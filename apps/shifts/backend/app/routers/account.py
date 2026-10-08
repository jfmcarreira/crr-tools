from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..security import hash_password, verify_password
from .dependencies import _check_csrf, _context, _flash, _redirect, _require_user, _safe_back

router = APIRouter()

@router.get("/account", response_class=HTMLResponse)
def account_page(request: Request, db: Session = Depends(get_db)):
    """The password editor lives on its own page, reached by clicking the user name."""
    _require_user(request, db)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="account.html",
        context=_context(request, db),
    )


@router.post("/account")
def account_password(
    request: Request,
    new_password: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """A user changes its own password from `/account`: one field, no ceremony."""
    _check_csrf(request, csrf_token)
    user = _require_user(request, db)
    if verify_password(new_password, user.password_hash):
        _flash(request, "A nova palavra-passe é igual à atual.", "error")
        return _redirect(_safe_back(request, "/"))
    try:
        user.password_hash = hash_password(new_password)
    except ValueError as exc:
        _flash(request, str(exc), "error")
        return _redirect(_safe_back(request, "/"))
    db.commit()
    _flash(request, "Palavra-passe alterada.")
    return _redirect(_safe_back(request, "/"))


@router.post("/account/email")
def account_email(
    request: Request,
    email: str = Form(""),
    notify_email: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """The address every notification for this user is sent to, kept by its owner."""
    _check_csrf(request, csrf_token)
    user = _require_user(request, db)
    value = email.strip().lower() or None
    if value and db.scalar(select(User.id).where(User.email == value, User.id != user.id)):
        _flash(request, "Esse endereço de e-mail já está a ser usado.", "error")
        return _redirect("/account")
    user.email = value
    user.notify_email = bool(notify_email)
    db.commit()
    _flash(request, "Notificações por e-mail atualizadas.")
    return _redirect("/account")
