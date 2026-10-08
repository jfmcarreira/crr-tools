from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from ..config import settings
from ..database import get_db
from ..models import Assignment, SwapRequest, Team
from ..i18n import day_numeric_long, day_short, month_name
from ..services.notifications import send_email_notification, send_many
from ..services.scheduling import ensure_month_assignments, in_scheduling_window, scheduling_horizon
from .admin.user_helpers import _admin_teams
from .dependencies import _beyond_horizon_message, _check_csrf, _context, _flash, _month_nav, _parse_month, _redirect, _require_admin, _require_user, _safe_back, _user_label, _user_team_ids
from .schedule_helpers import _active_schedules, _schedule_teams_map
from .swap_helpers import _accepting_team, _active_request, _complete_swap, _reject_swap, _rejectable, _swap_ownership_holds, _swap_partner, _swap_side

router = APIRouter()

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
    horizon = scheduling_horizon()
    groups: list[dict] = []
    for schedule in _active_schedules(db):
        mine = [
            a for a in assignments
            if a.schedule_id == schedule.id
            and a.team_id
            and (a.team_id in my_ids or user.is_admin)
            and a.date >= date.today()
            and a.date <= horizon
            and a.id not in taken
        ]
        theirs = [
            a for a in assignments
            if a.schedule_id == schedule.id
            and a.team_id
            and a.team_id not in my_ids
            and a.date >= date.today()
            and a.date <= horizon
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
    today = date.today()
    if (prev[0], prev[1]) < (today.year, today.month):
        prev = (today.year, today.month)
    if (nxt[0], nxt[1]) > (horizon.year, horizon.month):
        nxt = (horizon.year, horizon.month)
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
    if assignment.date > scheduling_horizon():
        raise HTTPException(status_code=400, detail=_beyond_horizon_message())
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
    for side in (swap.assignment, incoming):
        if side is not None and not in_scheduling_window(side.date):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Turnos passados não podem ser alterados"
                    if side.date < date.today()
                    else _beyond_horizon_message()
                ),
            )
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
