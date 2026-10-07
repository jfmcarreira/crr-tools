from __future__ import annotations

import calendar
from collections.abc import Sequence
import secrets
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from .calendar import build_feed
from .config import settings
from .database import get_db
from .models import (
    Assignment,
    User,
    MonthlyPattern,
    NotificationLog,
    RotationMember,
    Schedule,
    SwapRequest,
    Team,
)
from .i18n import (
    MONTHS,
    day_numeric,
    day_numeric_long,
    day_short,
    month_name,
    weekday_names,
    window_label,
)
from .notifications import send_email_notification, send_many
from .pdf import build_schedule_pdf
from .scheduling import (
    assignments_by_date,
    ensure_month_assignments,
    month_bounds,
    pattern_teams,
    rotation_team_for_date,
)
from .security import hash_password, new_csrf_token, verify_password

router = APIRouter()


def _redirect(path: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(settings.url(path), status_code=status_code)


def _parse_time(value: str) -> time:
    try:
        return time.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Hora inválida")


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


@router.get("/export/schedule", response_class=HTMLResponse)
def export_schedule(
    request: Request,
    schedule_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Choose a schedule and exact dates before downloading its PDF."""
    user = _require_user(request, db)
    schedules = _active_schedules(db)
    if not schedules:
        raise HTTPException(status_code=404, detail="Não há escalas ativas")
    if schedule_id is None:
        schedule = schedules[0]
    else:
        schedule = _get_schedule(db, schedule_id)
        if not schedule.is_active:
            raise HTTPException(status_code=404, detail="Escala não encontrada")

    if user.is_admin:
        return _redirect(f"/admin/schedules?schedule_id={schedule.id}#export-pdf")

    today = date.today()
    start, end = month_bounds(today.year, today.month)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="export_schedule.html",
        context=_context(
            request,
            db,
            schedules=schedules,
            selected_schedule_id=schedule.id,
            start=start.isoformat(),
            end=end.isoformat(),
        ),
    )


@router.get("/export/schedule.pdf")
def download_schedule_pdf(
    request: Request,
    schedule_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
):
    user = _require_user(request, db)
    schedule = _get_schedule(db, schedule_id)
    if not schedule.is_active:
        raise HTTPException(status_code=404, detail="Escala não encontrada")
    error = None
    if not (2000 <= start_date.year <= 2100 and 2000 <= end_date.year <= 2100):
        error = "Escolhe datas entre 2000 e 2100."
    elif end_date < start_date:
        error = "A data final deve ser igual ou posterior à data inicial."
    elif (end_date.year - start_date.year) * 12 + end_date.month - start_date.month >= 12:
        error = "Escolhe um intervalo de no máximo 12 meses."
    if error:
        if user.is_admin:
            return _render_admin_schedules(
                request, db, schedule.id, start_date, end_date, error, status_code=400,
            )
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="export_schedule.html",
            status_code=400,
            context=_context(
                request,
                db,
                schedules=_active_schedules(db),
                selected_schedule_id=schedule.id,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                error=error,
            ),
        )

    # Generate chronologically, keeping existing manual and swapped assignments.
    first = start_date.year * 12 + start_date.month - 1
    last = end_date.year * 12 + end_date.month - 1
    assignments: list[Assignment] = []
    for index in range(first, last + 1):
        year, month = divmod(index, 12)
        assignments.extend(
            row for row in ensure_month_assignments(db, year, month + 1)
            if row.schedule_id == schedule.id and start_date <= row.date <= end_date
        )
    filename = f"escala-{schedule.id}-{start_date.isoformat()}-{end_date.isoformat()}.pdf"
    return Response(
        content=build_schedule_pdf(schedule, assignments, start_date, end_date),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/health")
def health():
    return {"status": "ok"}


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


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
):
    user = _current_user(request, db)
    if user and not user.is_active:
        user = None
    my_ids = _user_team_ids(db, user)
    year, month = _parse_month(year, month)
    assignments = ensure_month_assignments(db, year, month)
    grouped = assignments_by_date(assignments)
    prev, nxt = _month_nav(year, month)

    my_assignment_ids = {a.id for a in assignments if a.team_id in my_ids}
    open_swap_assignment_ids = set()
    admin_requests: dict[int, SwapRequest] = {}
    if my_ids:
        open_swap_assignment_ids = set(
            db.scalars(
                select(SwapRequest.assignment_id).where(
                    SwapRequest.requester_id.in_(my_ids),
                    SwapRequest.status.in_(["open", "pending_approval"]),
                )
            ).all()
        )
    if user and user.is_admin:
        # Administrators can settle any request on this month's rota.
        admin_requests = {
            request.assignment_id: request
            for request in db.scalars(
                select(SwapRequest)
                .where(
                    SwapRequest.assignment_id.in_([a.id for a in assignments]),
                    SwapRequest.status.in_(["open", "pending_approval"]),
                )
                .options(
                    selectinload(SwapRequest.assignment).selectinload(Assignment.schedule),
                    selectinload(SwapRequest.target_assignment).selectinload(Assignment.schedule),
                    selectinload(SwapRequest.requester),
                    selectinload(SwapRequest.accepted_by),
                )
                .order_by(SwapRequest.created_at)
            ).all()
        }

    today = date.today()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=_context(
            request,
            db,
            year=year,
            month=month,
            month_name=month_name(month),
            month_days=[(date(year, month, d), grouped.get(date(year, month, d), [])) for d in range(1, calendar.monthrange(year, month)[1] + 1)],
            grouped=grouped,
            my_assignment_ids=my_assignment_ids,
            open_swap_assignment_ids=open_swap_assignment_ids,
            admin_requests=admin_requests,
            prev=prev,
            nxt=nxt,
            schedule_teams=_schedule_teams_map(
                db, {request.assignment.schedule_id for request in admin_requests.values()}
            ),
            today=today,
        ),
    )


@router.get("/swaps", response_class=HTMLResponse)
def swaps_page(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    my_ids = _user_team_ids(db, user)
    query = (
        select(SwapRequest)
        .options(
            selectinload(SwapRequest.assignment).selectinload(Assignment.schedule),
            selectinload(SwapRequest.requester),
            selectinload(SwapRequest.target_team),
            selectinload(SwapRequest.accepted_by),
        )
        .order_by(SwapRequest.created_at.desc())
    )
    if not user.is_admin:
        # A user sees and answers everything that involves the teams assigned to it.
        query = query.where(
            (SwapRequest.requester_id.in_(my_ids))
            | (SwapRequest.target_team_id.in_(my_ids))
            | ((SwapRequest.target_team_id.is_(None)) & (SwapRequest.status == "open"))
            | (SwapRequest.accepted_team_id.in_(my_ids))
        )
    swaps = db.scalars(query).all()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="swaps.html",
        context=_context(
            request,
            db,
            swaps=swaps,
            today=date.today(),
            schedule_teams=_schedule_teams_map(
                db, {swap.assignment.schedule_id for swap in swaps}
            ),
        ),
    )


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
    if _active_request(db, assignment.id):
        raise HTTPException(status_code=400, detail="Esse turno já tem um pedido de troca")
    return assignment


def _swap_partner(db: Session, schedule: Schedule, team_id: int | None) -> Team | None:
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


@router.get("/swaps/new", response_class=HTMLResponse)
def new_swap_page(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
):
    """Its own page, so the rota keeps showing only who works each day."""
    user = _require_user(request, db)
    my_ids = _user_team_ids(db, user)
    year, month = _parse_month(year, month)
    assignments = ensure_month_assignments(db, year, month)
    taken = set(
        db.scalars(
            select(SwapRequest.assignment_id).where(
                SwapRequest.status.in_(["open", "pending_approval"])
            )
        ).all()
    )
    # One team can work several days, so the shift to offer is chosen here,
    # and each schedule only offers the teams who work that same schedule.
    names = {t.id: t.name for t in db.scalars(select(Team)).all()}
    groups: list[dict] = []
    for schedule in _active_schedules(db):
        mine = [
            a for a in assignments
            if a.schedule_id == schedule.id
            and a.team_id
            and (a.team_id in my_ids or user.is_admin)
            and a.date >= date.today()
            and a.id not in taken
        ]
        theirs = [
            a for a in assignments
            if a.schedule_id == schedule.id
            and a.team_id
            and a.team_id not in my_ids
            and a.date >= date.today()
            and a.id not in taken
        ]
        if not mine or not theirs:
            continue
        groups.append(
            {
                "schedule": schedule,
                "shifts": [
                    {"id": a.id, "label": f"{day_short(a.date)} · {names[a.team_id]}"}
                    for a in sorted(mine, key=lambda r: r.date)
                ],
                "wanted": [
                    {
                        "id": a.id,
                        "label": f"{day_short(a.date)} · {names[a.team_id]}",
                    }
                    for a in sorted(theirs, key=lambda r: r.date)
                ],
            }
        )
    prev, nxt = _month_nav(year, month)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="swap_new.html",
        context=_context(
            request,
            db,
            year=year,
            month=month,
            month_name=month_name(month),
            prev=prev,
            nxt=nxt,
            groups=groups,
        ),
    )


@router.post("/swaps/new")
def create_swap_for_chosen_shift(
    request: Request,
    assignment_id: int = Form(...),
    target_assignment_id: int = Form(...),
    message: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    return _create_swap(assignment_id, request, target_assignment_id, message, csrf_token, db)


@router.post("/assignments/{assignment_id}/swap")
def create_swap(
    assignment_id: int,
    request: Request,
    target_assignment_id: int = Form(...),
    message: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    return _create_swap(assignment_id, request, target_assignment_id, message, csrf_token, db)


def _create_swap(
    assignment_id: int,
    request: Request,
    target_assignment_id: int,
    message: str,
    csrf_token: str,
    db: Session,
):
    _check_csrf(request, csrf_token)
    user = _require_user(request, db)
    my_ids = _user_team_ids(db, user)
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Turno não encontrado")
    # An administrator may open a request for someone else, but the shift stays
    # the requester's own so the ownership rule still applies on acceptance.
    owner_id = assignment.team_id
    if owner_id is None or (owner_id not in my_ids and not user.is_admin):
        raise HTTPException(status_code=403, detail="Só pode oferecer o turno da sua equipa")
    owner = db.get(Team, owner_id)
    if assignment.date < date.today():
        raise HTTPException(status_code=400, detail="Turnos passados não podem ser alterados")
    if _active_request(db, assignment.id):
        _flash(request, "Já existe um pedido de troca ativo para este turno.", "error")
        return _redirect("/swaps")

    # A swap is one shift for one shift, both of the same schedule.
    incoming = _swap_side(db, assignment.schedule, target_assignment_id, exclude_team_id=owner.id)
    if incoming.id == assignment.id:
        raise HTTPException(status_code=400, detail="Escolha outro turno para a troca")
    target = db.get(Team, incoming.team_id)

    swap = SwapRequest(
        assignment_id=assignment.id,
        target_assignment_id=incoming.id,
        requester_id=owner.id,
        target_team_id=target.id,
        status="open",
        message=message.strip() or None,
    )
    db.add(swap)
    db.commit()

    subject = (
        f"Troca de turnos: {day_short(assignment.date)} por {day_short(incoming.date)} "
        f"– {assignment.schedule.name}"
    )
    body = (
        f"{owner.name} propõe trocar o turno de {assignment.schedule.name} de "
        f"{day_numeric_long(assignment.date)} pelo seu turno de {day_numeric_long(incoming.date)}.\n\n"
        f"{message.strip()}\n\n"
        f"Abrir a escala: {settings.normalized_base_url}/swaps"
    )
    send_email_notification(db, target, "swap_requested", subject, body)

    _flash(request, "Pedido de troca criado.")
    return _redirect("/swaps")


def _safe_back(request: Request, fallback: str) -> str:
    """Return to the rota when the action was started there, never to an arbitrary URL."""
    back = str(request.query_params.get("back") or request.headers.get("referer") or "")
    if back.startswith("/") and not back.startswith("//"):
        return back.split("#")[0]
    return fallback


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


def _admin_teams(db: Session) -> list[Team]:
    """Every active team whose user is an administrator."""
    return list(
        db.scalars(
            select(Team)
            .join(User, Team.user_id == User.id)
            .where(
                User.is_admin.is_(True),
                User.is_active.is_(True),
                Team.is_active.is_(True),
            )
            .order_by(Team.name)
        ).all()
    )


@router.post("/swaps/{swap_id}/accept")
def accept_swap(
    swap_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    user = _require_user(request, db)
    my_ids = _user_team_ids(db, user)
    swap = db.scalar(
        select(SwapRequest)
        .where(SwapRequest.id == swap_id)
        .options(
            selectinload(SwapRequest.assignment).selectinload(Assignment.schedule),
            selectinload(SwapRequest.target_assignment).selectinload(Assignment.schedule),
            selectinload(SwapRequest.requester),
        )
    )
    if not swap or swap.status != "open":
        raise HTTPException(status_code=400, detail="Este pedido já não está aberto")
    if swap.requester_id in my_ids:
        raise HTTPException(status_code=400, detail="Não pode aceitar o seu próprio pedido")
    if swap.target_team_id is not None and swap.target_team_id not in my_ids:
        raise HTTPException(status_code=403, detail="Este pedido é para outra equipa")
    if not _swap_ownership_holds(db, swap):
        swap.status = "cancelled"
        db.commit()
        raise HTTPException(status_code=409, detail="O turno já foi alterado")

    team = _accepting_team(db, user, swap)
    swap.accepted_team_id = team.id
    if swap.assignment.schedule.requires_manager_approval:
        swap.status = "pending_approval"
        db.commit()
        admins = _admin_teams(db)
        send_many(
            db,
            admins,
            "swap_needs_approval",
            "Uma troca de turno precisa de aprovação",
            f"{team.name} aceitou a troca de {swap.assignment.schedule.name} de "
            f"{day_numeric_long(swap.assignment.date)}"
            + (
                f" por {day_numeric_long(swap.target_assignment.date)}"
                if swap.target_assignment is not None
                else ""
            )
            + f", pedida por {swap.requester.name}. Aprove em {settings.normalized_base_url}/swaps",
        )
        send_email_notification(
            db,
            swap.requester,
            "swap_accepted",
            "A sua troca de turno foi aceite",
            f"{team.name} aceitou o seu pedido. Está agora à espera da aprovação da gestão.",
        )
        _flash(request, "Aceite. A aguardar aprovação da gestão.")
    else:
        _complete_swap(db, swap, team)
        incoming = swap.target_assignment
        for recipient, other in ((swap.requester, team), (team, swap.requester)):
            send_email_notification(
                db,
                recipient,
                "swap_approved",
                "Troca de turno confirmada",
                f"Troca concluída em {swap.assignment.schedule.name}: fica com o turno de "
                f"{day_numeric_long(swap.assignment.date)}"
                + (
                    f" e passa o de {day_numeric_long(incoming.date)} para {other.name}."
                    if incoming is not None
                    else "."
                ),
            )
        _flash(request, "Troca concluída.")
    return _redirect("/swaps")


@router.post("/swaps/{swap_id}/reject")
def reject_swap(
    swap_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    user = _require_user(request, db)
    my_ids = _user_team_ids(db, user)
    swap = db.scalar(
        select(SwapRequest)
        .where(SwapRequest.id == swap_id)
        .options(selectinload(SwapRequest.requester))
    )
    if not swap or swap.status not in {"open", "pending_approval"}:
        raise HTTPException(status_code=400, detail="Este pedido já não está aberto")
    if not _rejectable(user, my_ids, swap):
        raise HTTPException(status_code=403, detail="Não pode recusar este pedido")
    who = _user_label(user)
    _reject_swap(db, swap)
    send_email_notification(
        db,
        swap.requester,
        "swap_rejected",
        "Pedido de troca recusado",
        f"{who} recusou o seu pedido de troca.",
    )
    _flash(request, "Pedido recusado.")
    return _redirect(_safe_back(request, "/swaps"))


@router.post("/swaps/{swap_id}/cancel")
def cancel_swap(
    swap_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    user = _require_user(request, db)
    my_ids = _user_team_ids(db, user)
    swap = db.get(SwapRequest, swap_id)
    if not swap or swap.requester_id not in my_ids or swap.status not in {"open", "pending_approval"}:
        raise HTTPException(status_code=403, detail="Não é possível cancelar este pedido")
    swap.status = "cancelled"
    db.commit()
    _flash(request, "Pedido cancelado.")
    return _redirect("/swaps")


@router.post("/swaps/{swap_id}/approve")
def approve_swap(
    swap_id: int,
    request: Request,
    team_id: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    _check_csrf(request, csrf_token)
    swap = db.scalar(
        select(SwapRequest)
        .where(SwapRequest.id == swap_id)
        .options(
            selectinload(SwapRequest.assignment).selectinload(Assignment.schedule),
            selectinload(SwapRequest.target_assignment).selectinload(Assignment.schedule),
            selectinload(SwapRequest.requester),
            selectinload(SwapRequest.accepted_by),
        )
    )
    if not swap or swap.status not in {"open", "pending_approval"}:
        raise HTTPException(status_code=400, detail="Este pedido já não pode ser aprovado")
    if not _swap_ownership_holds(db, swap):
        swap.status = "cancelled"
        db.commit()
        raise HTTPException(status_code=409, detail="O turno já foi alterado")
    if swap.assignment.date < date.today():
        raise HTTPException(status_code=400, detail="Turnos passados não podem ser alterados")

    if swap.accepted_by and swap.accepted_by.is_active:
        new_team = swap.accepted_by
    elif swap.target_team_id and db.get(Team, swap.target_team_id).is_active:
        new_team = db.get(Team, swap.target_team_id)
    else:
        new_team = _swap_partner(db, swap.assignment.schedule, int(team_id) if team_id.strip() else None)
    if new_team.id == swap.requester_id:
        raise HTTPException(status_code=400, detail="Escolha outra equipa para a troca")

    _complete_swap(db, swap, new_team)
    incoming = swap.target_assignment
    subject = "Troca de turno aprovada"
    body = (
        f"{_user_label(admin)} aprovou a troca de {swap.assignment.schedule.name}: "
        f"{new_team.name} fica com o turno de {day_numeric_long(swap.assignment.date)}"
        + (
            f" e {swap.requester.name} com o de {day_numeric_long(incoming.date)}."
            if incoming is not None
            else "."
        )
    )
    send_many(db, [swap.requester, new_team], "swap_approved", subject, body)
    _flash(request, "Troca aprovada e escala atualizada.")
    return _redirect(_safe_back(request, "/swaps"))


@router.post("/swaps/{swap_id}/revert")
def revert_swap(
    swap_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """Administrator only: undo an approved swap and give both shifts back."""
    admin = _require_admin(request, db)
    _check_csrf(request, csrf_token)
    swap = db.scalar(
        select(SwapRequest)
        .where(SwapRequest.id == swap_id)
        .options(
            selectinload(SwapRequest.assignment).selectinload(Assignment.schedule),
            selectinload(SwapRequest.target_assignment),
            selectinload(SwapRequest.requester),
        )
    )
    if not swap or swap.target_assignment_id is None:
        raise HTTPException(status_code=404, detail="Troca não encontrada")
    if swap.status != "approved":
        raise HTTPException(status_code=400, detail="Só uma troca aprovada pode ser revertida")
    # The shifts must still be the ones the swap produced, or somebody edited them since.
    if swap.assignment.team_id != swap.accepted_team_id or (
        swap.target_assignment is not None
        and swap.target_assignment.team_id != swap.requester_id
    ):
        raise HTTPException(
            status_code=409, detail="O turno foi alterado depois da troca; reverta com a atribuição por dia"
        )

    incoming = swap.target_assignment
    note = f"Revertida a troca #{swap.id} por {_user_label(admin)}"
    swap.assignment.team_id = swap.requester_id
    swap.assignment.source = "manual"
    swap.assignment.note = note
    incoming.team_id = swap.target_team_id
    incoming.source = "manual"
    incoming.note = note
    swap.status = "reverted"
    db.commit()

    subject = "Troca de turno revertida"
    body = (
        f"{_user_label(admin)} reverteu a troca de {swap.assignment.schedule.name}. "
        f"{swap.requester.name} volta a {day_numeric_long(swap.assignment.date)} e "
        f"{swap.target_team.name} volta a {day_numeric_long(incoming.date)}.\n\n"
        f"Ver a escala: {settings.normalized_base_url}/"
    )
    send_many(db, [swap.requester, swap.target_team], "swap_reverted", subject, body)
    _flash(request, "Troca revertida: os dois turnos voltaram a quem os tinha.")
    return _redirect(_safe_back(request, "/swaps"))


@router.post("/swaps/{swap_id}/admin-reject")
def admin_reject_swap(
    swap_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    _check_csrf(request, csrf_token)
    swap = db.scalar(
        select(SwapRequest)
        .where(SwapRequest.id == swap_id)
        .options(selectinload(SwapRequest.requester), selectinload(SwapRequest.accepted_by))
    )
    if not swap or swap.status not in {"open", "pending_approval"}:
        raise HTTPException(status_code=400, detail="Este pedido não pode ser recusado")
    _reject_swap(db, swap)
    involved = [t for t in [swap.requester, swap.accepted_by] if t]
    send_many(db, involved, "swap_rejected", "Troca de turno não aprovada",
              f"{_user_label(admin)} não aprovou a troca de turno pedida.")
    _flash(request, "Troca recusada.")
    return _redirect(_safe_back(request, "/swaps"))


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


def _usable_admin_users(db: Session, exclude: User | None = None) -> list[User]:
    """Administrator users that can still sign in: active, and covering an active team."""
    users = db.scalars(
        select(User)
        .where(User.is_admin.is_(True), User.is_active.is_(True))
        .options(selectinload(User.teams))
    ).all()
    return [
        user
        for user in users
        if user.id != (exclude.id if exclude else None)
        and any(team.is_active for team in user.teams)
    ]


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
    team_ids: list[str] = Form([]),
    is_admin: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """A new user, assigned to the teams it will sign in for."""
    _check_csrf(request, csrf_token)
    _require_admin(request, db)
    user, error = _new_user(db, name, username, password, is_admin=bool(is_admin))
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
    db: Session, name: str, username: str, password: str, *, is_admin: bool
) -> tuple[User | None, str | None]:
    """A user with a username and a password, unsaved, or the reason it was refused."""
    value = username.strip().lower()
    if not value:
        return None, "Defina um nome de utilizador."
    if db.scalar(select(User.id).where(User.username == value)):
        return None, "Esse nome de utilizador já existe."
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        return None, str(exc)
    return (
        User(
            name=name.strip() or value,
            username=value,
            password_hash=password_hash,
            is_admin=is_admin,
            is_active=True,
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
    team_ids: list[str] = Form([]),
    is_admin: str = Form(""),
    is_active: str = Form(""),
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
    user.is_admin = bool(is_admin)
    user.is_active = True if user.id == admin.id else bool(is_active)
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
    db.delete(user)
    db.commit()
    _flash(request, "Utilizador removido.")
    return _redirect("/admin/users")


@router.get("/admin/schedules", response_class=HTMLResponse)
def admin_schedules(
    request: Request,
    schedule_id: int | None = None,
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    return _render_admin_schedules(request, db, schedule_id)


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


@router.get("/admin/schedules/{schedule_id}", response_class=HTMLResponse)
def admin_schedule(
    schedule_id: int,
    request: Request,
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    schedule = _get_schedule(db, schedule_id)
    teams = db.scalars(select(Team).where(Team.is_active.is_(True)).order_by(Team.name)).all()
    year, month = _parse_month(year, month)
    assignments: list[Assignment] = []
    prev = nxt = (year, month)
    if schedule.schedule_type == "rotation":
        assignments = [
            row for row in ensure_month_assignments(db, year, month) if row.schedule_id == schedule.id
        ]
        prev, nxt = _month_nav(year, month)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin_schedule.html",
        context=_context(
            request,
            db,
            card=_schedule_card(schedule, db),
            cards=_schedule_groups(_all_schedules(db), db),
            teams=teams,
            schedule_teams=_schedule_teams(db, schedule.id),
            assignments=assignments,
            swap_requests=_open_swap_requests(db, schedule.id),
            pattern_days=list(range(1, 32)),
            pattern=_pattern_map(db, schedule),
            months=MONTHS,
            year=year,
            month=month,
            month_name=month_name(month),
            prev=prev,
            nxt=nxt,
        ),
    )


def _open_swap_requests(db: Session, schedule_id: int) -> list[SwapRequest]:
    """Open and pending change requests for one schedule, oldest first."""
    return list(
        db.scalars(
            select(SwapRequest)
            .where(
                SwapRequest.assignment_id.in_(
                    select(Assignment.id).where(Assignment.schedule_id == schedule_id)
                ),
                SwapRequest.status.in_(["open", "pending_approval"]),
            )
            .options(
                selectinload(SwapRequest.assignment).selectinload(Assignment.schedule),
                selectinload(SwapRequest.target_assignment).selectinload(Assignment.schedule),
                selectinload(SwapRequest.requester),
                selectinload(SwapRequest.target_team),
                selectinload(SwapRequest.accepted_by),
            )
            .order_by(SwapRequest.created_at)
        ).all()
    )


def _pattern_map(db: Session, schedule: Schedule) -> dict[int, int]:
    rows = db.scalars(
        select(MonthlyPattern).where(MonthlyPattern.schedule_id == schedule.id)
    ).all()
    return {row.day_of_month: row.team_id for row in rows if row.team_id is not None}


@router.post("/admin/schedules/{schedule_id}/pattern")
async def admin_schedule_pattern(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    form = await request.form()
    _check_csrf(request, str(form.get("csrf_token", "")))
    schedule = _get_schedule(db, schedule_id)
    if schedule.schedule_type == "rotation":
        raise HTTPException(status_code=400, detail="As rotações usam a sua própria ordem, não um padrão mensal")
    teams_by_id = {t.id for t in db.scalars(select(Team).where(Team.is_active.is_(True))).all()}

    existing = {
        row.day_of_month: row
        for row in db.scalars(
            select(MonthlyPattern).where(MonthlyPattern.schedule_id == schedule.id)
        ).all()
    }
    saved = 0
    for day in range(1, 32):
        raw = str(form.get(f"day_{day}", "")).strip()
        team_id = int(raw) if raw else None
        if team_id is not None and team_id not in teams_by_id:
            continue
        row = existing.get(day)
        if row is None:
            if team_id is None:
                continue
            db.add(MonthlyPattern(schedule_id=schedule.id, day_of_month=day, team_id=team_id))
            saved += 1
        elif row.team_id != team_id:
            row.team_id = team_id
            saved += 1
    db.commit()
    touched = _apply_pattern_to_open_rows(db, schedule)
    _flash(
        request,
        f"Padrão de noites guardado ({saved} alteração(ões)). "
        f"Foram atualizados {touched} turno(s) sem atribuição neste mês e no próximo; "
        f"as noites já atribuídas foram mantidas.",
    )
    return _redirect(f"/admin/schedules/{schedule.id}")


def _apply_pattern_to_open_rows(db: Session, schedule: Schedule) -> int:
    """Fill empty generated nights from the pattern; never touch existing assignees."""
    patterns = _pattern_map(db, schedule)
    if not patterns:
        return 0
    today = date.today()
    last_month = (today.month % 12) + 1
    last_year = today.year + (1 if today.month == 12 else 0)
    rows = db.scalars(
        select(Assignment).where(
            Assignment.schedule_id == schedule.id,
            Assignment.team_id.is_(None),
            Assignment.source == "generated",
            Assignment.date >= today.replace(day=1),
            Assignment.date <= date(last_year, last_month, calendar.monthrange(last_year, last_month)[1]),
        )
    ).all()
    touched = 0
    for row in rows:
        team_id = patterns.get(row.date.day)
        if team_id and row.team_id != team_id:
            row.team_id = team_id
            touched += 1
    if touched:
        db.commit()
    return touched


def _apply_pattern_forward(db: Session, schedule: Schedule, first: date) -> int:
    """Explicit admin edit: push the monthly pattern onto generated assignments from `first` on.

    Never creates or deletes rows, keeps assignment IDs, and preserves manual
    assignments and completed swaps. A day with nobody in the pattern is left as
    it is, so an empty pattern entry cannot blank out a shift.
    """
    patterns = pattern_teams(db, schedule)
    if not patterns:
        return 0
    rows = db.scalars(
        select(Assignment)
        .where(
            Assignment.schedule_id == schedule.id,
            Assignment.date >= first,
            Assignment.source == "generated",
        )
        .options(selectinload(Assignment.team), selectinload(Assignment.schedule))
        .order_by(Assignment.date)
    ).all()
    changed: list[tuple[Assignment, Team | None, Team | None]] = []
    touched = 0
    for row in rows:
        team_id = patterns.get(row.date.day)
        if team_id is None or row.team_id == team_id:
            continue
        old_team = db.get(Team, row.team_id) if row.team_id is not None else None
        new_team = db.get(Team, team_id)
        changed.append((row, old_team, new_team))
        for swap in db.scalars(
            select(SwapRequest).where(
                SwapRequest.assignment_id == row.id,
                SwapRequest.status.in_(["open", "pending_approval"]),
            )
        ).all():
            swap.status = "cancelled"
        row.team_id = team_id
        row.team = new_team
        touched += 1
    if changed:
        db.commit()
        _notify_assignment_changes(db, changed)
    return touched


@router.post("/admin/schedules/{schedule_id}/apply-pattern")
def admin_apply_pattern(
    schedule_id: int,
    request: Request,
    year: int = Form(...),
    month: int = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    _check_csrf(request, csrf_token)
    schedule = _get_schedule(db, schedule_id)
    if schedule.schedule_type != "fixed":
        raise HTTPException(status_code=400, detail="Esta escala não usa um padrão mensal")
    year, month = _parse_month(year, month)
    first = date(year, month, 1)
    touched = _apply_pattern_forward(db, schedule, first)
    _flash(
        request,
        f"Padrão aplicado a partir de {day_numeric_long(first)}: {touched} turno(s) atualizado(s). "
        f"As atribuições manuais e as trocas foram mantidas, e os dias sem equipa no padrão ficaram como estão.",
    )
    return _redirect(f"/admin/schedules/{schedule.id}")


def _clear_assignments_from(db: Session, schedule: Schedule, first: date) -> int:
    """Explicit admin edit: leave the shifts from `first` on without an assignee.

    Only `generated` rows are touched, so manual assignments and completed swaps
    survive. Rows keep their IDs, notes and swap history and stay `generated`, so
    applying the rotation again fills them.
    """
    rows = db.scalars(
        select(Assignment)
        .where(
            Assignment.schedule_id == schedule.id,
            Assignment.date >= first,
            Assignment.source == "generated",
            Assignment.team_id.is_not(None),
        )
        .options(selectinload(Assignment.team), selectinload(Assignment.schedule))
        .order_by(Assignment.date)
    ).all()
    changed: list[tuple[Assignment, Team | None, Team | None]] = []
    for row in rows:
        old_team = db.get(Team, row.team_id)
        changed.append((row, old_team, None))
        for swap in db.scalars(
            select(SwapRequest).where(
                SwapRequest.assignment_id == row.id,
                SwapRequest.status.in_(["open", "pending_approval"]),
            )
        ).all():
            swap.status = "cancelled"
        row.team_id = None
        row.team = None
    if changed:
        db.commit()
        _notify_assignment_changes(db, changed)
    return len(changed)


@router.post("/admin/schedules/{schedule_id}/clear-from")
def admin_clear_from(
    schedule_id: int,
    request: Request,
    year: int = Form(...),
    month: int = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    _check_csrf(request, csrf_token)
    schedule = _get_schedule(db, schedule_id)
    if schedule.schedule_type != "rotation":
        raise HTTPException(status_code=400, detail="Esta escala não usa rotação")
    year, month = _parse_month(year, month)
    first = date(year, month, 1)
    cleared = _clear_assignments_from(db, schedule, first)
    _flash(
        request,
        f"Turnos limpos a partir de {day_numeric_long(first)}: {cleared} turno(s) sem atribuição. "
        f"As atribuições manuais e as trocas foram mantidas. Use Aplicar rotação para os preencher de novo.",
    )
    return _redirect(f"/admin/schedules/{schedule.id}?year={year}&month={month}")


@router.post("/admin/schedules/{schedule_id}/settings")
def admin_schedule_settings(
    schedule_id: int,
    request: Request,
    requires_manager_approval: str = Form(""),
    is_active: str = Form(""),
    start_time: str = Form(""),
    end_time: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    _require_admin(request, db)
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Escala não encontrada")
    if start_time and end_time:
        schedule.start_time = _parse_time(start_time)
        schedule.end_time = _parse_time(end_time)
    schedule.requires_manager_approval = bool(requires_manager_approval)
    schedule.is_active = bool(is_active)
    db.commit()
    _flash(request, "Definições da escala guardadas.")
    return _redirect(f"/admin/schedules/{schedule.id}")


@router.post("/admin/schedules/{schedule_id}/rotation")
def admin_rotation_add(
    schedule_id: int,
    request: Request,
    team_id: int = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    _require_admin(request, db)
    schedule = db.get(Schedule, schedule_id)
    user = db.get(Team, team_id)
    if not schedule or schedule.schedule_type != "rotation" or not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Membro da rotação inválido")
    exists = db.scalar(
        select(RotationMember.id).where(
            RotationMember.schedule_id == schedule.id,
            RotationMember.team_id == user.id,
        )
    )
    if exists:
        _flash(request, "Essa equipa já está nesta rotação.", "error")
        return _redirect(f"/admin/schedules/{schedule.id}#rotation-order")
    max_position = db.scalar(
        select(func.max(RotationMember.position)).where(RotationMember.schedule_id == schedule.id)
    ) or 0
    db.add(RotationMember(schedule_id=schedule.id, team_id=user.id, position=max_position + 1))
    db.commit()
    _flash(request, "Membro adicionado à rotação.")
    return _redirect(f"/admin/schedules/{schedule.id}#rotation-order")


@router.post("/admin/rotation/{member_id}/remove")
def admin_rotation_remove(
    member_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    _require_admin(request, db)
    member = db.get(RotationMember, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Membro da rotação não encontrado")
    schedule_id = member.schedule_id
    db.delete(member)
    db.commit()
    members = db.scalars(
        select(RotationMember).where(RotationMember.schedule_id == schedule_id).order_by(RotationMember.position)
    ).all()
    for idx, row in enumerate(members, start=1):
        row.position = idx
    db.commit()
    _flash(request, "Membro removido da rotação.")
    return _redirect(f"/admin/schedules/{schedule_id}")


@router.post("/admin/rotation/{member_id}/move")
def admin_rotation_move(
    member_id: int,
    request: Request,
    direction: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    _require_admin(request, db)
    member = db.get(RotationMember, member_id)
    if not member or direction not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="Movimento inválido")
    target_position = member.position - 1 if direction == "up" else member.position + 1
    other = db.scalar(
        select(RotationMember).where(
            RotationMember.schedule_id == member.schedule_id,
            RotationMember.position == target_position,
        )
    )
    if other:
        temporary = 1000000 + member.id
        member.position = temporary
        db.flush()
        other.position = target_position + 1 if direction == "up" else target_position - 1
        db.flush()
        member.position = target_position
        db.commit()
    return _redirect(f"/admin/schedules/{member.schedule_id}")


@router.get("/admin/month", response_class=HTMLResponse)
def admin_month(request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    # Each schedule is now configured on its own page.
    return _redirect("/admin/schedules")


def _save_assignments(db: Session, assignments: Sequence[Assignment], form) -> int:
    teams_by_id = {t.id: t for t in db.scalars(select(Team).where(Team.is_active.is_(True))).all()}
    changed: list[tuple[Assignment, Team | None, Team | None]] = []
    for assignment in assignments:
        raw = str(form.get(f"assignment_{assignment.id}", "")).strip()
        new_team_id = int(raw) if raw else None
        if new_team_id is not None and new_team_id not in teams_by_id:
            continue
        if assignment.team_id != new_team_id:
            old_team = assignment.team
            new_team = teams_by_id.get(new_team_id) if new_team_id else None
            assignment.team_id = new_team_id
            assignment.source = "manual"
            changed.append((assignment, old_team, new_team))
    db.commit()

    _notify_assignment_changes(db, changed)
    return len(changed)


def _default_team(db: Session, schedule: Schedule, day: date) -> Team | None:
    """Who this shift would have by default: the rotation order or the night pattern."""
    if schedule.schedule_type == "rotation":
        return rotation_team_for_date(db, schedule, day)
    team_id = _pattern_map(db, schedule).get(day.day)
    return db.get(Team, team_id) if team_id else None


def _set_assignee(
    db: Session, assignment: Assignment, new_team: Team | None, source: str = "manual"
) -> None:
    """Put someone on a shift directly: no change request, and any stale one is closed."""
    assignment.team_id = new_team.id if new_team else None
    assignment.team = new_team
    assignment.source = source
    for swap in db.scalars(
        select(SwapRequest).where(
            SwapRequest.status.in_(["open", "pending_approval"]),
            (SwapRequest.assignment_id == assignment.id)
            | (SwapRequest.target_assignment_id == assignment.id),
        )
    ).all():
        swap.status = "cancelled"
    db.commit()


def _notify_assignment_changes(db: Session, changed: Sequence[tuple[Assignment, Team | None, Team | None]]) -> None:
    for assignment, old_team, new_team in changed:
        subject = f"Escala atualizada: {day_short(assignment.date)} – {assignment.schedule.name}"
        if new_team:
            send_email_notification(
                db,
                new_team,
                "assignment_updated",
                subject,
                f"Está atribuído ao turno de {assignment.schedule.name} a {day_numeric_long(assignment.date)}.\n\n"
                f"Ver a escala: {settings.normalized_base_url}/",
            )
        if old_team and (not new_team or old_team.id != new_team.id):
            send_email_notification(
                db,
                old_team,
                "assignment_changed",
                subject,
                f"Já não está atribuído ao turno de {assignment.schedule.name} a {day_numeric_long(assignment.date)}.\n\n"
                f"Ver a escala: {settings.normalized_base_url}/",
            )


def _month_assignments(db: Session, year: int, month: int) -> list[Assignment]:
    first, last = month_bounds(year, month)
    return list(
        db.scalars(
            select(Assignment)
            .where(Assignment.date >= first, Assignment.date <= last)
            .options(selectinload(Assignment.team), selectinload(Assignment.schedule))
            .order_by(Assignment.date)
        ).all()
    )


@router.post("/admin/schedules/{schedule_id}/swaps/{swap_id}/assign")
def admin_schedule_assign_swap(
    schedule_id: int,
    swap_id: int,
    request: Request,
    team_id: int = Form(...),
    year: str = Form(""),
    month: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """Complete a change request on behalf of the rota, including for rota-only teams."""
    admin = _require_admin(request, db)
    _check_csrf(request, csrf_token)
    schedule = _get_schedule(db, schedule_id)
    swap = db.scalar(
        select(SwapRequest)
        .where(SwapRequest.id == swap_id)
        .options(
            selectinload(SwapRequest.assignment).selectinload(Assignment.schedule),
            selectinload(SwapRequest.target_assignment).selectinload(Assignment.schedule),
            selectinload(SwapRequest.requester),
        )
    )
    if not swap or swap.assignment.schedule_id != schedule.id:
        raise HTTPException(status_code=404, detail="Pedido de troca não encontrado")
    if swap.status not in {"open", "pending_approval"}:
        raise HTTPException(status_code=400, detail="Este pedido já não está aberto")
    new_team = _swap_partner(db, schedule, team_id)
    if new_team.id == swap.requester_id:
        raise HTTPException(status_code=400, detail="Escolha outra equipa para a troca")
    if swap.assignment.date < date.today():
        raise HTTPException(status_code=400, detail="Turnos passados não podem ser alterados")
    # The request only applies while the team who asked for the change still owns the shift.
    if not _swap_ownership_holds(db, swap):
        swap.status = "cancelled"
        db.commit()
        raise HTTPException(status_code=409, detail="O turno já foi alterado")

    swap.assignment.team_id = new_team.id
    swap.assignment.source = "swap"
    swap.accepted_team_id = new_team.id
    swap.status = "approved"
    for other in db.scalars(
        select(SwapRequest).where(
            SwapRequest.assignment_id == swap.assignment_id,
            SwapRequest.id != swap.id,
            SwapRequest.status.in_(["open", "pending_approval"]),
        )
    ).all():
        other.status = "cancelled"
    db.commit()

    subject = "Troca de turno aprovada"
    body = (
        f"{_user_label(admin)} atribuiu o turno de {schedule.name} de "
        f"{day_numeric_long(swap.assignment.date)} a {new_team.name}, a pedido de {swap.requester.name}."
        + (
            f" Em troca, {swap.requester.name} passa a ter o turno de "
            f"{day_numeric_long(swap.target_assignment.date)}."
            if swap.target_assignment is not None
            else ""
        )
        + f"\n\nVer a escala: {settings.normalized_base_url}/"
    )
    send_many(db, [swap.requester, new_team], "swap_approved", subject, body)
    _flash(request, f"Turno de {day_short(swap.assignment.date)} atribuído a {new_team.name}.")
    return _redirect(f"{_schedule_page(schedule.id, year, month)}#swap-requests")


def _schedule_page(schedule_id: int, year: str, month: str) -> str:
    if year.isdigit() and month.isdigit():
        return f"/admin/schedules/{schedule_id}?year={int(year)}&month={int(month)}"
    return f"/admin/schedules/{schedule_id}"


@router.post("/admin/schedules/{schedule_id}/assignments")
async def admin_schedule_assignments(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    form = await request.form()
    _check_csrf(request, str(form.get("csrf_token", "")))
    schedule = _get_schedule(db, schedule_id)
    year = int(form.get("year", date.today().year))
    month = int(form.get("month", date.today().month))
    assignments = [row for row in _month_assignments(db, year, month) if row.schedule_id == schedule.id]
    changed = _save_assignments(db, assignments, form)
    _flash(request, f"Foram guardadas {changed} alteração(ões) de turno.")
    return _redirect(f"/admin/schedules/{schedule.id}?year={year}&month={month}")


def _apply_rotation_to_rows(db: Session, schedule: Schedule, assignments: Sequence[Assignment]) -> int:
    """Explicit admin edit: retain assignment IDs and invalidate requests when ownership changes."""
    changed: list[tuple[Assignment, Team | None, Team | None]] = []
    touched = 0
    db.flush()
    for assignment in sorted(assignments, key=lambda row: row.date):
        new_team = rotation_team_for_date(db, schedule, assignment.date)
        new_team_id = new_team.id if new_team else None
        if assignment.team_id == new_team_id and assignment.source == "generated":
            continue
        if assignment.team_id != new_team_id:
            old_team = db.get(Team, assignment.team_id) if assignment.team_id is not None else None
            changed.append((assignment, old_team, new_team))
            if assignment.id is not None:
                requests = db.scalars(select(SwapRequest).where(
                    SwapRequest.assignment_id == assignment.id,
                    SwapRequest.status.in_(["open", "pending_approval"]),
                )).all()
                for swap in requests:
                    swap.status = "cancelled"
        assignment.team_id = new_team_id
        assignment.team = new_team
        assignment.source = "generated"
        # Later dates continue from the team selected for this date.
        db.flush()
        touched += 1
    db.commit()
    _notify_assignment_changes(db, changed)
    return touched


def _generate_rotation_range(db: Session, schedule: Schedule, first: date, last: date) -> tuple[int, int]:
    rows = {row.date: row for row in db.scalars(
        select(Assignment)
        .where(Assignment.schedule_id == schedule.id, Assignment.date >= first, Assignment.date <= last)
        .options(selectinload(Assignment.team), selectinload(Assignment.schedule))
    ).all()}
    assignments = []
    created = 0
    day = first
    while day <= last:
        if day.weekday() not in schedule.weekday_set:
            day += timedelta(days=1)
            continue
        row = rows.get(day)
        if row is None:
            row = Assignment(schedule=schedule, date=day, source="generated")
            db.add(row)
            created += 1
        if row.source == "generated":
            assignments.append(row)
        day += timedelta(days=1)
    changed = _apply_rotation_to_rows(db, schedule, assignments)
    return created, changed


@router.post("/admin/schedules/{schedule_id}/apply-rotation")
def admin_apply_rotation(
    schedule_id: int,
    request: Request,
    year: int = Form(...),
    month: int = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    _check_csrf(request, csrf_token)
    schedule = _get_schedule(db, schedule_id)
    if schedule.schedule_type != "rotation":
        raise HTTPException(status_code=400, detail="Esta escala não usa rotação")
    year, month = _parse_month(year, month)
    created, changed = _generate_rotation_range(db, schedule, *month_bounds(year, month))
    _flash(request, f"Rotação aplicada em {month_name(month)} de {year}: "
           f"{created} turno(s) criado(s), {changed} turno(s) atualizado(s). "
           f"As atribuições manuais e as trocas foram mantidas.")
    return _redirect(f"/admin/schedules/{schedule.id}?year={year}&month={month}")


@router.post("/admin/schedules/{schedule_id}/assignments/{assignment_id}/regenerate")
@router.post("/admin/schedules/{schedule_id}/assignments/{assignment_id}/use-rotation")
def admin_assignment_regenerate(
    schedule_id: int,
    assignment_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    _check_csrf(request, csrf_token)
    schedule = _get_schedule(db, schedule_id)
    if schedule.schedule_type != "rotation":
        raise HTTPException(status_code=400, detail="Esta escala não usa rotação")
    assignment = db.get(Assignment, assignment_id)
    if assignment is None or assignment.schedule_id != schedule.id:
        raise HTTPException(status_code=404, detail="Turno não encontrado")
    if assignment.date.weekday() not in schedule.weekday_set:
        raise HTTPException(status_code=400, detail="Esta data não corresponde à escala")
    _apply_rotation_to_rows(db, schedule, [assignment])
    _flash(request, "Turno recalculado com a equipa a seguir à responsável pelo turno anterior.")
    return _redirect(f"/admin/schedules/{schedule.id}?year={assignment.date.year}&month={assignment.date.month}")


@router.get("/admin/assign", response_class=HTMLResponse)
def admin_assign_day(
    request: Request,
    on: str | None = None,
    db: Session = Depends(get_db),
):
    """Pick a day and put someone on one of its shifts. No change request involved.

    `on` is a whole ISO date (`YYYY-MM-DD`), which is what the date input sends.
    """
    _require_admin(request, db)
    today = date.today()
    chosen = today
    if on:
        try:
            chosen = date.fromisoformat(on)
        except ValueError:
            raise HTTPException(status_code=400, detail="Data inválida")
    rows = {
        a.schedule_id: a
        for a in ensure_month_assignments(db, chosen.year, chosen.month)
        if a.date == chosen
    }
    shifts = [
        {
            "schedule": schedule,
            "assignment": rows[schedule.id],
            "auto": _default_team(db, schedule, chosen),
        }
        for schedule in _active_schedules(db)
        if schedule.id in rows
    ]
    prev_day = chosen - timedelta(days=1)
    next_day = chosen + timedelta(days=1)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin_assign.html",
        context=_context(
            request,
            db,
            day=chosen,
            shifts=shifts,
            teams=db.scalars(
                select(Team).where(Team.is_active.is_(True)).order_by(Team.name)
            ).all(),
            prev_day=prev_day,
            next_day=next_day,
            today=today,
        ),
    )


@router.post("/admin/assign")
def admin_assign_team(
    request: Request,
    assignment_id: int = Form(...),
    team_id: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    _check_csrf(request, csrf_token)
    assignment = db.scalar(
        select(Assignment)
        .where(Assignment.id == assignment_id)
        .options(selectinload(Assignment.schedule), selectinload(Assignment.team))
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Turno não encontrado")
    if assignment.date.weekday() not in assignment.schedule.weekday_set:
        raise HTTPException(status_code=400, detail="Esta data não corresponde à escala")

    choice = team_id.strip()
    source = "manual"
    new_team = None
    if choice == "auto":
        source = "generated"
        new_team = _default_team(db, assignment.schedule, assignment.date)
    elif choice:
        new_team = db.get(Team, int(choice))
        if not new_team or not new_team.is_active:
            raise HTTPException(status_code=400, detail="Equipa inválida")
    if new_team and new_team.id == assignment.team_id and assignment.source == source:
        _flash(request, f"{new_team.name} já estava em {day_short(assignment.date)}.")
        return _redirect(_assign_day_url(assignment.date))

    previous_team_id = assignment.team_id
    _set_assignee(db, assignment, new_team, source)
    previous_team = db.get(Team, previous_team_id) if previous_team_id else None
    _notify_assignment_changes(db, [(assignment, previous_team, new_team)])
    if new_team is None:
        message = f"Turno de {day_short(assignment.date)} sem atribuição."
    else:
        message = f"{new_team.name} em {day_short(assignment.date)} · {assignment.schedule.name}."
        if source == "generated":
            message += " (automático)"
    _flash(request, message)
    return _redirect(_assign_day_url(assignment.date))


def _assign_day_url(day: date) -> str:
    return f"/admin/assign?on={day.isoformat()}"


@router.get("/admin/notifications", response_class=HTMLResponse)
def admin_notifications(request: Request, db: Session = Depends(get_db)):
    _require_admin(request, db)
    logs = db.scalars(
        select(NotificationLog)
        .options(selectinload(NotificationLog.team))
        .order_by(NotificationLog.created_at.desc())
        .limit(200)
    ).all()
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="admin_notifications.html",
        context=_context(request, db, logs=logs),
    )
