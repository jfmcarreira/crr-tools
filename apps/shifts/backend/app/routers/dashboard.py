from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from ..database import get_db
from ..models import AccessPin, Assignment, SwapRequest
from ..config import settings
from ..services.door_access import LISBON_TZ, can_request_pin, expire_pins
from ..i18n import month_name
from ..services.scheduling import assignments_by_date, ensure_month_assignments, scheduling_horizon
from .dependencies import _context, _current_user, _month_nav, _parse_month, _require_user, _user_team_ids
from .schedule_helpers import _schedule_teams_map

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
):
    return _render_dashboard(request, year, month, db)


@router.get("/my-days", response_class=HTMLResponse)
def my_days(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
):
    return _render_dashboard(request, year, month, db, personal=True)


def _render_dashboard(
    request: Request,
    year: int | None,
    month: int | None,
    db: Session,
    *,
    personal: bool = False,
):
    user = _require_user(request, db) if personal else _current_user(request, db)
    if user and not user.is_active:
        user = None
    my_ids = _user_team_ids(db, user)
    year, month = _parse_month(year, month)
    if personal:
        assignments = list(db.scalars(
            select(Assignment)
            .where(
                Assignment.team_id.in_(my_ids),
                Assignment.date >= date.today(),
                Assignment.date <= scheduling_horizon(),
            )
            .options(selectinload(Assignment.team), selectinload(Assignment.schedule))
            .order_by(Assignment.date, Assignment.schedule_id)
        ).all())
    else:
        assignments = ensure_month_assignments(db, year, month)
    grouped = assignments_by_date(assignments)
    if personal:
        month_days = sorted(grouped.items())
    else:
        month_days = [
            (date(year, month, d), grouped.get(date(year, month, d), []))
            for d in range(1, calendar.monthrange(year, month)[1] + 1)
        ]
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
    now = datetime.now(timezone.utc)
    active_pins = []
    expired_pins = []
    access_assignments = []
    if user:
        expire_pins(db, now)
        user_pins = db.scalars(select(AccessPin).where(AccessPin.user_id == user.id)).all()
        active_pins = [pin for pin in user_pins if pin.status == "active"]
        expired_pins = sorted(
            [pin for pin in user_pins if pin.status == "expired"], key=lambda pin: pin.id, reverse=True,
        )[:5]
        issued = {pin.assignment_id for pin in user_pins if pin.lock_id == settings.ttlock_lock_id}
        if settings.ttlock_enabled and user.can_request_pin:
            local_today = now.astimezone(LISBON_TZ).date()
            candidates = db.scalars(select(Assignment).where(
                Assignment.team_id.in_(my_ids),
                Assignment.date.in_([local_today, local_today - timedelta(days=1)]),
            )).all()
            access_assignments = [a for a in candidates if a.id not in issued and can_request_pin(db, user, a.id, now)]
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        context=_context(
            request,
            db,
            year=year,
            month=month,
            month_name=month_name(month),
            month_names={m: month_name(m) for m in range(1, 13)},
            personal=personal,
            dashboard_path="/my-days" if personal else "/",
            month_days=month_days,
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
            active_pins=active_pins,
            expired_pins=expired_pins,
            access_assignments=access_assignments,
        ),
    )
