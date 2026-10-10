from datetime import date, datetime, time, timezone

from sqlalchemy import select

from app.models import Assignment, Schedule, Team, User
from app.services.door_access import can_request_pin


def test_user_creation_defaults_pin_permission_disabled(db):
    user = User(
        name="Teste",
        username="teste",
        password_hash="hash",
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    db.flush()
    assert user.can_request_pin is False


def test_can_request_pin_requires_permission_and_window(db, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "ttlock_eligible_schedule_slugs", "almoco")
    user = User(
        name="Operador",
        username="operador",
        password_hash="hash",
        is_admin=False,
        is_active=True,
        can_request_pin=True,
    )
    team = Team(name="Equipa A", user=user, is_active=True)
    schedule = Schedule(
        name="Almoço",
        slug="almoco",
        schedule_type="fixed",
        weekdays="5",
        start_time=time(13, 0),
        end_time=time(16, 0),
        requires_manager_approval=False,
        is_active=True,
    )
    assignment = Assignment(date=date(2026, 10, 10), schedule=schedule, team=team, source="generated")
    db.add_all([user, team, schedule, assignment])
    db.commit()

    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)  # 13:00 Lisbon, at shift start
    assert can_request_pin(db, user, assignment.id, now) is True

    user.can_request_pin = False
    db.commit()
    assert can_request_pin(db, user, assignment.id, now) is False

    user.can_request_pin = True
    db.commit()
    later = datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc)
    assert can_request_pin(db, user, assignment.id, later) is False
