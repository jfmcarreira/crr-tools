import calendar
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assignment, Schedule, SwapRequest, Team
from app.routers.swap_helpers import _complete_swap
from app.services.scheduling import (
    ensure_month_assignments,
    in_scheduling_window,
    month_bounds,
    scheduling_horizon,
)


def _csrf(client: TestClient) -> str:
    page = client.get("/admin/schedules")
    assert page.status_code == 200
    return page.text.split('name="csrf_token" value="')[1].split('"')[0]


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return divmod(index, 12)[0], divmod(index, 12)[1] + 1


def _month_rows(db: Session, schedule: Schedule, year: int, month: int) -> list[Assignment]:
    ensure_month_assignments(db, year, month)
    first, last = month_bounds(year, month)
    return db.scalars(
        select(Assignment).where(
            Assignment.schedule_id == schedule.id,
            Assignment.date >= first,
            Assignment.date <= last,
        )
    ).all()


def test_window_helpers_match_end_of_sixth_month() -> None:
    """The horizon is the last day of the 6th month ahead, both limits included."""
    today = date.today()
    horizon = scheduling_horizon()
    year, month = _shift_month(today.year, today.month, 6)
    assert horizon == date(year, month, calendar.monthrange(year, month)[1])
    assert in_scheduling_window(today)
    assert in_scheduling_window(horizon)
    assert not in_scheduling_window(today - timedelta(days=1))
    assert not in_scheduling_window(horizon + timedelta(days=1))


def test_admin_save_refuses_past_and_beyond_month(
    db: Session, logged_in: TestClient, schedule: Schedule
) -> None:
    horizon = scheduling_horizon()
    past_year, past_month = _shift_month(date.today().year, date.today().month, -2)
    next_year, next_month = _shift_month(horizon.year, horizon.month, 1)

    past = logged_in.post(
        f"/admin/schedules/{schedule.id}/assignments",
        data={"year": str(past_year), "month": str(past_month),
              "csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert past.status_code == 400
    assert "Turnos passados não podem ser alterados" in past.text

    beyond = logged_in.post(
        f"/admin/schedules/{schedule.id}/assignments",
        data={"year": str(next_year), "month": str(next_month),
              "csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert beyond.status_code == 400
    assert "Só é possível agendar turnos" in beyond.text


def test_admin_assign_refuses_past_and_beyond_day(
    db: Session, logged_in: TestClient, schedule: Schedule, team: Team
) -> None:
    horizon = scheduling_horizon()
    past_year, past_month = _shift_month(date.today().year, date.today().month, -2)
    next_year, next_month = _shift_month(horizon.year, horizon.month, 1)
    past_row = min(_month_rows(db, schedule, past_year, past_month), key=lambda row: row.date)
    beyond_row = min(_month_rows(db, schedule, next_year, next_month), key=lambda row: row.date)
    assert past_row.date < date.today()
    assert beyond_row.date > horizon

    past = logged_in.post(
        "/admin/assign",
        data={"assignment_id": str(past_row.id), "team_id": str(team.id),
              "csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert past.status_code == 400
    assert "Turnos passados não podem ser alterados" in past.text

    beyond = logged_in.post(
        "/admin/assign",
        data={"assignment_id": str(beyond_row.id), "team_id": str(team.id),
              "csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert beyond.status_code == 400
    assert "Só é possível agendar turnos" in beyond.text


def test_admin_apply_pattern_refuses_beyond_month(
    db: Session, logged_in: TestClient, team: Team
) -> None:
    horizon = scheduling_horizon()
    fixed = Schedule(name="Noite de teste", slug="noite-teste", schedule_type="fixed",
                     weekdays="0,1,2,3,4,5,6", rotation_anchor_date=None)
    db.add(fixed)
    db.commit()
    next_year, next_month = _shift_month(horizon.year, horizon.month, 1)

    response = logged_in.post(
        f"/admin/schedules/{fixed.id}/apply-pattern",
        data={"year": str(next_year), "month": str(next_month),
              "csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Só é possível agendar turnos" in response.text


def test_admin_clear_from_and_apply_rotation_refuse_beyond_month(
    db: Session, logged_in: TestClient, schedule: Schedule
) -> None:
    horizon = scheduling_horizon()
    next_year, next_month = _shift_month(horizon.year, horizon.month, 1)

    cleared = logged_in.post(
        f"/admin/schedules/{schedule.id}/clear-from",
        data={"year": str(next_year), "month": str(next_month),
              "csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert cleared.status_code == 400
    assert "Só é possível agendar turnos" in cleared.text

    rotated = logged_in.post(
        f"/admin/schedules/{schedule.id}/apply-rotation",
        data={"year": str(next_year), "month": str(next_month),
              "csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert rotated.status_code == 400
    assert "Só é possível agendar turnos" in rotated.text


def test_admin_regenerate_refuses_beyond_row(
    db: Session, logged_in: TestClient, schedule: Schedule
) -> None:
    horizon = scheduling_horizon()
    next_year, next_month = _shift_month(horizon.year, horizon.month, 1)
    beyond_row = min(_month_rows(db, schedule, next_year, next_month), key=lambda row: row.date)

    response = logged_in.post(
        f"/admin/schedules/{schedule.id}/assignments/{beyond_row.id}/regenerate",
        data={"csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Só é possível agendar turnos" in response.text


def test_create_swap_refuses_beyond_shifts(
    db: Session, logged_in: TestClient, schedule: Schedule, team: Team
) -> None:
    """Both the offered shift and its target must stay inside the booking window."""
    other = Team(name="Equipa Sul")
    db.add(other)
    db.commit()

    today = date.today()
    offer = min(
        (row for row in _month_rows(db, schedule, today.year, today.month)
         if row.date >= today),
        key=lambda row: row.date,
    )
    offer.team_id = team.id

    horizon = scheduling_horizon()
    next_year, next_month = _shift_month(horizon.year, horizon.month, 1)
    beyond = min(_month_rows(db, schedule, next_year, next_month), key=lambda row: row.date)
    beyond.team_id = other.id
    db.commit()

    offer_beyond = logged_in.post(
        "/swaps/new",
        data={"assignment_id": str(beyond.id), "target_assignment_id": str(offer.id),
              "message": "", "csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert offer_beyond.status_code == 400
    assert "Só é possível agendar turnos" in offer_beyond.text

    target_beyond = logged_in.post(
        "/swaps/new",
        data={"assignment_id": str(offer.id), "target_assignment_id": str(beyond.id),
              "message": "", "csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert target_beyond.status_code == 400
    assert "Só é possível agendar turnos" in target_beyond.text


def test_complete_swap_refuses_out_of_window(
    db: Session, schedule: Schedule, team: Team
) -> None:
    """Accept/approve/admin-assign all settle through _complete_swap, so its guard
    protects every completion path against stale requests outside the window."""
    other = Team(name="Equipa Sul")
    db.add(other)
    db.commit()

    horizon = scheduling_horizon()
    next_year, next_month = _shift_month(horizon.year, horizon.month, 1)
    rows = _month_rows(db, schedule, next_year, next_month)
    assert len(rows) >= 2
    rows[0].team_id = team.id
    rows[1].team_id = other.id
    swap = SwapRequest(assignment_id=rows[0].id, target_assignment_id=rows[1].id,
                       requester_id=team.id, target_team_id=other.id, status="open")
    db.add(swap)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        _complete_swap(db, swap, other)
    assert "Só é possível agendar turnos" in str(exc.value.detail)
    db.refresh(rows[0])
    assert rows[0].team_id == team.id  # untouched by the refused completion


def test_swap_new_hides_beyond_months(
    db: Session, logged_in: TestClient, schedule: Schedule
) -> None:
    """The offer page stops at the horizon month and lists no far-future shifts."""
    horizon = scheduling_horizon()
    next_year, next_month = _shift_month(horizon.year, horizon.month, 1)

    beyond = logged_in.get(
        f"/swaps/new?year={next_year}&month={next_month}",
        follow_redirects=False,
    )
    assert beyond.status_code == 200
    assert "Não há turnos disponíveis" in beyond.text
    assert f"/swaps/new?year={next_year}&amp;month={next_month}" not in beyond.text

    at_horizon = logged_in.get(
        f"/swaps/new?year={horizon.year}&month={horizon.month}",
        follow_redirects=False,
    )
    # "Seguinte →" is clamped to the horizon month instead of escaping it.
    assert f"/swaps/new?year={horizon.year}&amp;month={horizon.month}" in at_horizon.text


def test_revert_swap_refuses_out_of_window(
    db: Session, logged_in: TestClient, schedule: Schedule, team: Team
) -> None:
    """Revert is also a rota change: refused when either shift sits outside the window."""
    other = Team(name="Equipa Sul")
    db.add(other)
    db.commit()

    horizon = scheduling_horizon()
    next_year, next_month = _shift_month(horizon.year, horizon.month, 1)
    rows = _month_rows(db, schedule, next_year, next_month)
    assert len(rows) >= 2
    rows[0].team_id = other.id
    rows[1].team_id = team.id
    swap = SwapRequest(
        assignment_id=rows[0].id,
        target_assignment_id=rows[1].id,
        requester_id=team.id,
        target_team_id=other.id,
        status="approved",
        accepted_team_id=other.id,
    )
    db.add(swap)
    db.commit()

    response = logged_in.post(
        f"/swaps/{swap.id}/revert",
        data={"csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Só é possível agendar turnos" in response.text
    db.refresh(rows[0])
    assert rows[0].team_id == other.id  # untouched by the refused revert


def test_admin_assign_navigation_clamps_at_horizon(
    db: Session, logged_in: TestClient, schedule: Schedule
) -> None:
    horizon = scheduling_horizon()

    at_horizon = logged_in.get(f"/admin/assign?on={horizon.isoformat()}", follow_redirects=False)
    assert at_horizon.status_code == 200
    assert "Dia anterior" in at_horizon.text
    assert "Dia seguinte" not in at_horizon.text

    beyond = logged_in.get(
        f"/admin/assign?on={(horizon + timedelta(days=1)).isoformat()}",
        follow_redirects=False,
    )
    assert beyond.status_code == 200
    assert "Data fora da janela de agendamento" in beyond.text
    assert "Sem edição" in beyond.text


def test_schedule_pages_render_in_and_out_of_window(
    db: Session, logged_in: TestClient, schedule: Schedule
) -> None:
    """The configuration page still renders read-only outside the window and
    keeps its editable grid inside it, for both kinds of schedule."""
    today = date.today()
    horizon = scheduling_horizon()
    next_year, next_month = _shift_month(horizon.year, horizon.month, 1)

    fixed = Schedule(name="Noite de teste", slug="noite-teste", schedule_type="fixed",
                     weekdays="0,1,2,3,4,5,6", rotation_anchor_date=None)
    db.add(fixed)
    db.commit()

    in_window = logged_in.get(
        f"/admin/schedules/{schedule.id}?year={today.year}&month={today.month}",
        follow_redirects=False,
    )
    assert in_window.status_code == 200
    assert "/apply-rotation" in in_window.text
    assert "Guardar" in in_window.text

    beyond = logged_in.get(
        f"/admin/schedules/{schedule.id}?year={next_year}&month={next_month}",
        follow_redirects=False,
    )
    assert beyond.status_code == 200
    assert "Mês fora da janela de agendamento" in beyond.text
    assert "/apply-rotation" not in beyond.text

    fixed_page = logged_in.get(
        f"/admin/schedules/{fixed.id}?year={next_year}&month={next_month}",
        follow_redirects=False,
    )
    assert fixed_page.status_code == 200