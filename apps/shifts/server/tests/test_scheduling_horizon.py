import calendar
import re
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assignment, Schedule, SwapRequest, Team, User
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
    """Completion must refuse existing shifts beyond the horizon."""
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
    db.refresh(rows[1])
    assert rows[0].team_id == team.id
    assert rows[1].team_id == other.id
    assert swap.status == "open"


def test_swap_new_hides_beyond_months(
    db: Session, logged_in: TestClient, schedule: Schedule
) -> None:
    """There is no month navigation or far-future shift selection."""
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
    assert "Seguinte →" not in at_horizon.text
    assert "Anterior" not in at_horizon.text


def test_swap_page_lists_existing_targets_across_months_without_generating(
    db: Session, logged_in: TestClient, schedule: Schedule, team: Team, admin: User
) -> None:
    team.user_id = admin.id
    admin.is_admin = False
    other = Team(name="Equipa Sul")
    another_schedule = Schedule(name="Outra escala", slug="outra", schedule_type="fixed", weekdays="5")
    db.add_all([other, another_schedule])
    db.flush()
    today = date.today()
    year, month = _shift_month(today.year, today.month, 2)
    future = date(year, month, 15)
    offer = Assignment(schedule_id=schedule.id, date=today, team_id=team.id)
    later_offer = Assignment(schedule_id=schedule.id, date=future - timedelta(days=1), team_id=team.id)
    wanted = Assignment(schedule_id=schedule.id, date=future, team_id=other.id)
    unassigned = Assignment(schedule_id=schedule.id, date=future + timedelta(days=1))
    past = Assignment(schedule_id=schedule.id, date=today - timedelta(days=1), team_id=other.id)
    wrong_schedule = Assignment(schedule_id=another_schedule.id, date=future, team_id=other.id)
    beyond = Assignment(
        schedule_id=schedule.id,
        date=scheduling_horizon() + timedelta(days=1),
        team_id=other.id,
    )
    db.add_all([offer, later_offer, wanted, unassigned, past, wrong_schedule, beyond])
    db.commit()
    before = set(db.scalars(select(Assignment.id)).all())

    page = logged_in.get(f"/swaps/new?year={today.year}&month={today.month}")
    assert page.status_code == 200
    offered_options = re.search(r'<select name="assignment_id" required>(.*?)</select>', page.text, re.S)
    wanted_options = re.search(r'<select name="target_assignment_id" required>(.*?)</select>', page.text, re.S)
    assert offered_options is not None and wanted_options is not None
    assert re.findall(r'<option value="(\d+)"', offered_options.group(1)) == [str(offer.id), str(later_offer.id)]
    assert re.findall(r'<option value="(\d+)"', wanted_options.group(1)) == [str(wanted.id)]
    assert set(db.scalars(select(Assignment.id)).all()) == before
    assert schedule.name in page.text
    assert another_schedule.name not in page.text
    assert "Seguinte →" not in page.text
    assert 'name="message"' not in page.text
    assert "Não consigo fazer este dia" not in page.text

    later_page = logged_in.get(f"/swaps/new?year={year}&month={month}")
    assert f'<option value="{wanted.id}">' in later_page.text
    assert f'<option value="{offer.id}">' in later_page.text

    beyond_page = logged_in.get(f"/swaps/new?year={beyond.date.year}&month={beyond.date.month}")
    assert f'<option value="{later_offer.id}">' in beyond_page.text
    assert f'<option value="{beyond.id}">' not in beyond_page.text

    response = logged_in.post(
        "/swaps/new",
        data={"assignment_id": offer.id, "target_assignment_id": wanted.id,
              "csrf_token": page.text.split('name="csrf_token" value="')[1].split('"')[0]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    swap = db.scalar(select(SwapRequest).where(SwapRequest.assignment_id == offer.id))
    assert swap is not None and swap.target_assignment_id == wanted.id
    assert swap.message is None
    _complete_swap(db, swap, other)
    db.refresh(offer)
    db.refresh(wanted)
    assert offer.team_id == other.id and wanted.team_id == team.id


@pytest.mark.parametrize("past_side", ["offered", "target"])
def test_complete_swap_still_refuses_past_shifts(
    db: Session, schedule: Schedule, team: Team, past_side: str
) -> None:
    other = Team(name="Equipa Sul")
    db.add(other)
    db.flush()
    today = date.today()
    offer = Assignment(
        schedule_id=schedule.id,
        date=today - timedelta(days=1) if past_side == "offered" else today,
        team_id=team.id,
    )
    target = Assignment(
        schedule_id=schedule.id,
        date=today - timedelta(days=1) if past_side == "target" else today + timedelta(days=1),
        team_id=other.id,
    )
    db.add_all([offer, target])
    db.flush()
    swap = SwapRequest(assignment_id=offer.id, target_assignment_id=target.id,
                       requester_id=team.id, target_team_id=other.id, status="open")
    db.add(swap)
    db.commit()
    with pytest.raises(HTTPException, match="Turnos passados"):
        _complete_swap(db, swap, other)
    assert offer.team_id == team.id and target.team_id == other.id


def test_revert_swap_refuses_out_of_window(
    db: Session, logged_in: TestClient, schedule: Schedule, team: Team
) -> None:
    """Revert refuses either shift beyond the scheduling horizon."""
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
    db.refresh(rows[1])
    db.refresh(swap)
    assert rows[0].team_id == other.id
    assert rows[1].team_id == team.id
    assert swap.status == "approved"


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
