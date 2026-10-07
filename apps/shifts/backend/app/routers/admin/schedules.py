from __future__ import annotations

from datetime import time
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from ...database import get_db
from ...models import Assignment, MonthlyPattern, RotationMember, Schedule, SwapRequest, Team
from ...i18n import MONTHS, month_name
from ...services.scheduling import ensure_month_assignments
from ..assignment_helpers import _apply_pattern_to_open_rows
from ..dependencies import _check_csrf, _context, _flash, _month_nav, _parse_month, _redirect, _require_admin
from ..schedule_helpers import _all_schedules, _get_schedule, _pattern_map, _render_admin_schedules, _schedule_card, _schedule_groups, _schedule_teams

router = APIRouter()

def _parse_time(value: str) -> time:
    try:
        return time.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Hora inválida")


@router.get("/admin/schedules", response_class=HTMLResponse)
def admin_schedules(
    request: Request,
    schedule_id: int | None = None,
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    return _render_admin_schedules(request, db, schedule_id)


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
