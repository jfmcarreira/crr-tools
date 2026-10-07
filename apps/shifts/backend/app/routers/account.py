from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from ..database import get_db
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
