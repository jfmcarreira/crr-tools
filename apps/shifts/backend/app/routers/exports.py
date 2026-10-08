from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Assignment
from ..services.pdf import build_schedule_pdf
from ..services.scheduling import ensure_month_assignments
from .dependencies import _redirect, _require_admin
from .schedule_helpers import _active_schedules, _get_schedule, _render_admin_schedules

router = APIRouter()

@router.get("/export/schedule", response_class=HTMLResponse)
def export_schedule(
    request: Request,
    schedule_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Choose a schedule and exact dates before downloading its PDF."""
    _require_admin(request, db)
    schedules = _active_schedules(db)
    if not schedules:
        raise HTTPException(status_code=404, detail="Não há escalas ativas")
    if schedule_id is None:
        schedule = schedules[0]
    else:
        schedule = _get_schedule(db, schedule_id)
        if not schedule.is_active:
            raise HTTPException(status_code=404, detail="Escala não encontrada")

    return _redirect(f"/admin/schedules?schedule_id={schedule.id}#export-pdf")


@router.get("/export/schedule.pdf")
def download_schedule_pdf(
    request: Request,
    schedule_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
):
    _require_admin(request, db)
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
        return _render_admin_schedules(
            request, db, schedule.id, start_date, end_date, error, status_code=400,
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
