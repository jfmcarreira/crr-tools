from __future__ import annotations

from datetime import date
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import settings
from ..models import Team, User
from ..security import new_csrf_token

def _redirect(path: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(settings.url(path), status_code=status_code)


def _current_user(request: Request, db: Session) -> User | None:
    """The user the session belongs to. One user can be assigned to several teams."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, int(user_id))


def _require_user(request: Request, db: Session) -> User:
    user = _current_user(request, db)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="É necessário iniciar sessão")
    return user


def _require_admin(request: Request, db: Session) -> User:
    user = _require_user(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="É necessária a permissão de administrador")
    return user


def _user_teams(db: Session, user: User | None) -> list[Team]:
    """The teams assigned to this user. A user sees and controls the rota of all of them."""
    if user is None:
        return []
    return list(
        db.scalars(select(Team).where(Team.user_id == user.id).order_by(Team.name)).all()
    )


def _user_team_ids(db: Session, user: User | None) -> set[int]:
    return {team.id for team in _user_teams(db, user)}


def _user_label(user: User) -> str:
    """How a user is named in messages and e-mails."""
    return user.name or user.username


def _csrf(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = new_csrf_token()
        request.session["csrf"] = token
    return token


def _check_csrf(request: Request, token: str) -> None:
    expected = request.session.get("csrf")
    if not expected or token != expected:
        raise HTTPException(status_code=400, detail="Token CSRF inválido")


def _flash(request: Request, message: str, level: str = "info") -> None:
    request.session["flash"] = {"message": message, "level": level}


def _context(request: Request, db: Session, **extra):
    user = _current_user(request, db)
    teams = _user_teams(db, user)
    return {
        "request": request,
        "settings": settings,
        "current_user": user,
        "current_teams": teams,
        "my_team_ids": {team.id for team in teams},
        "csrf_token": _csrf(request),
        "flash": request.session.pop("flash", None),
        **extra,
    }


def _parse_month(year: int | None, month: int | None) -> tuple[int, int]:
    today = date.today()
    y = year or today.year
    m = month or today.month
    if m < 1 or m > 12 or y < 2000 or y > 2100:
        raise HTTPException(status_code=400, detail="Mês inválido")
    return y, m


def _month_nav(year: int, month: int) -> tuple[tuple[int, int], tuple[int, int]]:
    if month == 1:
        prev = (year - 1, 12)
    else:
        prev = (year, month - 1)
    if month == 12:
        nxt = (year + 1, 1)
    else:
        nxt = (year, month + 1)
    return prev, nxt


def _safe_back(request: Request, fallback: str) -> str:
    """Return to the rota when the action was started there, never to an arbitrary URL."""
    back = str(request.query_params.get("back") or request.headers.get("referer") or "")
    if back.startswith("/") and not back.startswith("//"):
        return back.split("#")[0]
    return fallback
