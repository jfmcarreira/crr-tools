from __future__ import annotations

from collections.abc import Sequence
import secrets
from datetime import date, timedelta
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from ..config import settings
from ..models import Assignment, MonthlyPattern, RotationMember, Schedule, Team
from ..i18n import day_short, weekday_names
from ..services.scheduling import month_bounds
from .dependencies import _context

ALL_WEEKDAYS = frozenset(range(7))

def _next_dates(weekdays: set[int], count: int = 6) -> list[str]:
    today = date.today()
    labels: list[str] = []
    day = today
    while len(labels) < count:
        if day.weekday() in weekdays:
            labels.append(day_short(day))
        day += timedelta(days=1)
    return labels


def _schedule_card(schedule: Schedule, db: Session | None = None) -> dict:
    weekdays = schedule.weekday_set
    fixed = schedule.schedule_type != "rotation" and weekdays == ALL_WEEKDAYS
    if fixed:
        kind_label = "Todos os dias · repete todos os meses"
        weekday_label = "Todos os dias"
        dates: list[str] = []
    else:
        weekday_label = weekday_names(weekdays)
        kind_label = f"Rotação · {weekday_label}"
        dates = _next_dates(weekdays)
    pattern: list[tuple[int, str]] = []
    if fixed and db is not None:
        rows = db.scalars(
            select(MonthlyPattern)
            .where(MonthlyPattern.schedule_id == schedule.id)
            .options(selectinload(MonthlyPattern.team))
            .order_by(MonthlyPattern.day_of_month)
        ).all()
        pattern = [
            (row.day_of_month, row.team.name)
            for row in rows
            if row.team is not None and row.team.is_active
        ]
    return {
        "schedule": schedule,
        "kind": "fixed" if fixed else "rotation",
        "kind_label": kind_label,
        "weekday_label": weekday_label,
        "dates": dates,
        "pattern": pattern,
        "rotation_names": [member.team.name for member in schedule.rotation_members],
    }


def _schedule_groups(schedules: Sequence[Schedule], db: Session | None = None) -> list[dict]:
    cards = [_schedule_card(schedule, db) for schedule in schedules]
    # Every rotation is independent: Saturday and Sunday lunch never share an order.
    return sorted(cards, key=lambda card: (card["kind"] != "fixed", card["weekday_label"] != "Todos os dias"))


def _active_schedules(db: Session) -> list[Schedule]:
    return list(
        db.scalars(
            select(Schedule)
            .where(Schedule.is_active.is_(True))
            .options(selectinload(Schedule.rotation_members).selectinload(RotationMember.team))
            .order_by(Schedule.id)
        ).all()
    )


def _all_schedules(db: Session) -> list[Schedule]:
    return list(
        db.scalars(
            select(Schedule)
            .options(selectinload(Schedule.rotation_members).selectinload(RotationMember.team))
            .order_by(Schedule.id)
        ).all()
    )


def _get_schedule(db: Session, schedule_id: int) -> Schedule:
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Escala não encontrada")
    return schedule


def _schedule_team_ids(db: Session, schedule_id: int) -> set[int]:
    """Everyone who works this schedule: its rotation, its pattern or one of its shifts.

    A swap is always one team for one team of the same schedule, so these are
    the only teams who can be asked or chosen.
    """
    ids: set[int] = set()
    ids.update(
        db.scalars(
            select(Assignment.team_id).where(
                Assignment.schedule_id == schedule_id, Assignment.team_id.is_not(None)
            )
        ).all()
    )
    ids.update(
        db.scalars(
            select(MonthlyPattern.team_id).where(
                MonthlyPattern.schedule_id == schedule_id, MonthlyPattern.team_id.is_not(None)
            )
        ).all()
    )
    ids.update(
        db.scalars(select(RotationMember.team_id).where(RotationMember.schedule_id == schedule_id)).all()
    )
    return {i for i in ids if i is not None}


def _schedule_teams(db: Session, schedule_id: int) -> list[Team]:
    ids = _schedule_team_ids(db, schedule_id)
    if not ids:
        return []
    return list(
        db.scalars(
            select(Team).where(Team.id.in_(ids), Team.is_active.is_(True)).order_by(Team.name)
        ).all()
    )


def _schedule_teams_map(db: Session, schedule_ids: set[int]) -> dict[int, list[Team]]:
    """Active teams per schedule, for the swap forms: a swap stays inside one schedule."""
    return {schedule_id: _schedule_teams(db, schedule_id) for schedule_id in schedule_ids}


def _render_admin_schedules(
    request: Request,
    db: Session,
    schedule_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
    error: str | None = None,
    status_code: int = 200,
):
    cards = _schedule_groups(_all_schedules(db), db)
    schedules = [card["schedule"] for card in cards if card["schedule"].is_active]
    if schedule_id is not None:
        selected = _get_schedule(db, schedule_id)
        if not selected.is_active:
            raise HTTPException(status_code=404, detail="Escala não encontrada")
    else:
        selected = schedules[0] if schedules else None
    today = date.today()
    first, last = month_bounds(today.year, today.month)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin_schedules.html",
        status_code=status_code,
        context=_context(
            request,
            db,
            cards=cards,
            calendar_feed_url=_shared_calendar_url(request),
            schedules=schedules,
            selected_schedule_id=selected.id if selected else None,
            start=(start or first).isoformat(),
            end=(end or last).isoformat(),
            error=error,
        ),
    )


def _shared_calendar_url(request: Request) -> str:
    """The whole-rota feed, with a team token created the first time it is asked for."""
    if not settings.calendar_token:
        settings.calendar_token = secrets.token_urlsafe(24)
    path = settings.url(f"/calendar/{settings.calendar_token}.ics")
    return f"{request.base_url.scheme}://{request.base_url.netloc}{path}"


def _pattern_map(db: Session, schedule: Schedule) -> dict[int, int]:
    rows = db.scalars(
        select(MonthlyPattern).where(MonthlyPattern.schedule_id == schedule.id)
    ).all()
    return {row.day_of_month: row.team_id for row in rows if row.team_id is not None}
