from __future__ import annotations

from datetime import date, timedelta
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import FormData
from ...config import settings
from ...database import get_db
from ...models import Assignment, SwapRequest, Team
from ...i18n import day_numeric_long, day_short, month_name
from ...services.notifications import send_many
from ...services.scheduling import ensure_month_assignments, month_bounds, scheduling_horizon
from ..assignment_helpers import _apply_pattern_forward, _apply_rotation_to_rows, _clear_assignments_from, _default_team, _generate_rotation_range, _month_assignments, _notify_assignment_changes, _save_assignments, _set_assignee
from ..dependencies import _beyond_horizon_message, _check_csrf, _context, _flash, _parse_month, _raw_form, _redirect, _require_admin, _user_label
from ..schedule_helpers import _active_schedules, _get_schedule
from ..swap_helpers import _complete_swap, _swap_ownership_holds, _swap_partner

router = APIRouter()

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
    if first > scheduling_horizon():
        raise HTTPException(status_code=400, detail=_beyond_horizon_message())
    touched = _apply_pattern_forward(db, schedule, first)
    _flash(
        request,
        f"Padrão aplicado a partir de {day_numeric_long(first)}: {touched} turno(s) atualizado(s). "
        f"As atribuições manuais e as trocas foram mantidas, e os dias sem equipa no padrão ficaram como estão.",
    )
    return _redirect(f"/admin/schedules/{schedule.id}")


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
    if first > scheduling_horizon():
        raise HTTPException(status_code=400, detail=_beyond_horizon_message())
    cleared = _clear_assignments_from(db, schedule, first)
    _flash(
        request,
        f"Turnos limpos a partir de {day_numeric_long(first)}: {cleared} turno(s) sem atribuição. "
        f"As atribuições manuais e as trocas foram mantidas. Use Aplicar rotação para os preencher de novo.",
    )
    return _redirect(f"/admin/schedules/{schedule.id}?year={year}&month={month}")


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

    # Atomic two-sided swap: both shifts change hands, competing requests on
    # either side are cancelled, and the request is committed — exactly what
    # the team-side accept/approve paths do.
    _complete_swap(db, swap, new_team)

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


# Saving runs SQLite commits and one e-mail per change; as a sync endpoint
# FastAPI runs it in the threadpool, so it can never stall the event loop.
# The form itself is parsed by the async _raw_form dependency on the loop.
@router.post("/admin/schedules/{schedule_id}/assignments")
def admin_schedule_assignments(
    schedule_id: int,
    request: Request,
    form: FormData = Depends(_raw_form),
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
    _check_csrf(request, str(form.get("csrf_token", "")))
    schedule = _get_schedule(db, schedule_id)
    year = int(str(form.get("year", date.today().year)))
    month = int(str(form.get("month", date.today().month)))
    first, last = month_bounds(year, month)
    if last < date.today():
        raise HTTPException(status_code=400, detail="Turnos passados não podem ser alterados")
    if first > scheduling_horizon():
        raise HTTPException(status_code=400, detail=_beyond_horizon_message())
    assignments = [row for row in _month_assignments(db, year, month) if row.schedule_id == schedule.id]
    changed = _save_assignments(db, assignments, form)
    _flash(request, f"Foram guardadas {changed} alteração(ões) de turno.")
    return _redirect(f"/admin/schedules/{schedule.id}?year={year}&month={month}")


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
    first, last = month_bounds(year, month)
    if last < date.today():
        raise HTTPException(status_code=400, detail="Turnos passados não podem ser alterados")
    if first > scheduling_horizon():
        raise HTTPException(status_code=400, detail=_beyond_horizon_message())
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
    if assignment.date < date.today():
        raise HTTPException(status_code=400, detail="Turnos passados não podem ser alterados")
    if assignment.date > scheduling_horizon():
        raise HTTPException(status_code=400, detail=_beyond_horizon_message())
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
    horizon = scheduling_horizon()
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
    prev_day = chosen - timedelta(days=1) if chosen > today else chosen
    next_day = chosen + timedelta(days=1) if chosen < horizon else chosen
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
            horizon=horizon,
            editable=today <= chosen <= horizon,
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
    if assignment.date < date.today():
        raise HTTPException(status_code=400, detail="Turnos passados não podem ser alterados")
    if assignment.date > scheduling_horizon():
        raise HTTPException(status_code=400, detail=_beyond_horizon_message())
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
