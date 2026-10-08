"""Admin endpoints changed for atomic swaps and threadpool form handling."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assignment, MonthlyPattern, Schedule, SwapRequest, Team
from app.services.scheduling import ensure_month_assignments
from fastapi.testclient import TestClient


def _csrf(client: TestClient) -> str:
    page = client.get("/admin/schedules")
    assert page.status_code == 200
    return page.text.split('name="csrf_token" value="')[1].split('"')[0]


def _next_saturday(weeks_ahead: int) -> date:
    today = date.today()
    days = (5 - today.weekday()) % 7 or 7
    return today + timedelta(days=days + 7 * (weeks_ahead - 1))


def test_admin_assign_completes_both_sides(
    db: Session, logged_in: TestClient, schedule: Schedule, team: Team
) -> None:
    """The rota-side approval transfers the target shift back to the requester."""
    other = Team(name="Equipa Sul")
    db.add(other)
    db.commit()

    mine = Assignment(schedule_id=schedule.id, date=_next_saturday(1),
                      team_id=team.id, source="manual")
    theirs = Assignment(schedule_id=schedule.id, date=_next_saturday(2),
                        team_id=other.id, source="manual")
    db.add_all([mine, theirs])
    db.commit()

    competing = SwapRequest(assignment_id=theirs.id, requester_id=other.id, status="open")
    swap = SwapRequest(assignment_id=mine.id, target_assignment_id=theirs.id,
                       requester_id=team.id, target_team_id=other.id, status="open")
    db.add_all([competing, swap])
    db.commit()

    response = logged_in.post(
        f"/admin/schedules/{schedule.id}/swaps/{swap.id}/assign",
        data={"team_id": str(other.id), "csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert response.status_code == 303

    for row in (mine, theirs, swap, competing):
        db.refresh(row)
    # Both shifts changed hands: the requester receives the target shift too.
    assert mine.team_id == other.id and mine.source == "swap"
    assert theirs.team_id == team.id and theirs.source == "swap"
    assert swap.status == "approved" and swap.accepted_team_id == other.id
    # A competing request on either side of the swap is closed with it.
    assert competing.status == "cancelled"


def test_admin_save_assignments_endpoint(
    db: Session, logged_in: TestClient, schedule: Schedule, team: Team
) -> None:
    """The monthly grid saves through the threadpool-safe form dependency."""
    today = date.today()
    ensure_month_assignments(db, today.year, today.month)
    assignment = db.scalar(
        select(Assignment)
        .where(Assignment.schedule_id == schedule.id, Assignment.date >= today)
        .order_by(Assignment.date)
    )
    assert assignment is not None

    response = logged_in.post(
        f"/admin/schedules/{schedule.id}/assignments",
        data={
            f"assignment_{assignment.id}": str(team.id),
            "year": str(today.year),
            "month": str(today.month),
            "csrf_token": _csrf(logged_in),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db.refresh(assignment)
    assert assignment.team_id == team.id
    assert assignment.source == "manual"


def test_admin_pattern_endpoint(db: Session, logged_in: TestClient, team: Team) -> None:
    """The fixed-schedule night pattern saves through the same dependency."""
    fixed = Schedule(name="Noite de teste", slug="noite-teste", schedule_type="fixed",
                     weekdays="0,1,2,3,4,5,6", rotation_anchor_date=None)
    db.add(fixed)
    db.commit()

    response = logged_in.post(
        f"/admin/schedules/{fixed.id}/pattern",
        data={"day_1": str(team.id), "csrf_token": _csrf(logged_in)},
        follow_redirects=False,
    )
    assert response.status_code == 303

    row = db.scalar(select(MonthlyPattern).where(
        MonthlyPattern.schedule_id == fixed.id, MonthlyPattern.day_of_month == 1
    ))
    assert row is not None
    assert row.team_id == team.id
