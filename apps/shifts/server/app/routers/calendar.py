from __future__ import annotations

import secrets
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..services.calendar_feed import build_feed
from ..config import settings
from ..database import get_db
from ..models import Team
from .dependencies import _context, _require_user, _user_teams
from .schedule_helpers import _shared_calendar_url

router = APIRouter()

def _calendar_token(db: Session, team: Team) -> str:
    """A private feed token for this team, created the first time it is needed."""
    if not team.calendar_token:
        team.calendar_token = secrets.token_urlsafe(24)
        db.commit()
    return team.calendar_token


@router.get("/calendar/{token}.ics")
def calendar_feed(
    token: str,
    db: Session = Depends(get_db),
):
    """Subscribe from any calendar app: one feed per team, plus a shared whole-rota feed."""
    team = db.scalar(select(Team).where(Team.calendar_token == token, Team.is_active.is_(True)))
    shared = bool(settings.calendar_token) and token == settings.calendar_token
    if team is None and not shared:
        raise HTTPException(status_code=404, detail="Calendário não encontrado")
    name = f"{settings.app_name} — {team.name}" if team else settings.app_name
    return Response(
        content=build_feed(db, team, name),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="rota.ics"',
            "Cache-Control": "private, max-age=300",
        },
    )


@router.get("/calendar", response_class=HTMLResponse)
def calendar_page(request: Request, db: Session = Depends(get_db)):
    """The links to subscribe, kept off the rota so that page stays about the shifts."""
    user = _require_user(request, db)
    feeds = [
        {
            "title": f"Turnos de {team.name}",
            "url": f"{request.base_url.scheme}://{request.base_url.netloc}"
            f"{settings.url(f'/calendar/{_calendar_token(db, team)}.ics')}",
        }
        for team in _user_teams(db, user)
        if team.is_active
    ]
    if user.is_admin:
        feeds.append(
            {
                "title": "Rota completa",
                "url": _shared_calendar_url(request),
            }
        )
    for feed in feeds:
        feed["webcal_url"] = "webcal://" + feed["url"].split("://", 1)[-1]
        feed["google_url"] = "https://calendar.google.com/calendar/render?" + urlencode(
            {"cid": feed["url"]}
        )
        feed["outlook_url"] = "https://outlook.live.com/calendar/0/addfromweb?" + urlencode(
            {"url": feed["url"], "name": feed["title"]}
        )
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context=_context(request, db, feeds=feeds),
    )
