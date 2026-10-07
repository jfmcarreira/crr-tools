from __future__ import annotations

import calendar
from datetime import date
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from ..database import get_db
from ..models import Assignment, SwapRequest
from ..i18n import month_name
from ..services.scheduling import assignments_by_date, ensure_month_assignments
from .dependencies import _context, _current_user, _month_nav, _parse_month, _user_team_ids
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
