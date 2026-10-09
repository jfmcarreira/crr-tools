from __future__ import annotations

from datetime import date, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Schedule, Team, User
from ..security import MIN_PASSWORD_LENGTH, hash_password

# Values the app must never turn into a real administrator account.
_PLACEHOLDER_PASSWORDS = {"", "change-me-now"}


def _require_initial_password() -> None:
    """Refuse to bootstrap the admin with a known or trivial password."""
    password = settings.initial_admin_password.strip()
    if password in _PLACEHOLDER_PASSWORDS or len(password) < MIN_PASSWORD_LENGTH:
        raise RuntimeError(
            "INITIAL_ADMIN_PASSWORD não está definida (ou ainda é a palavra-passe "
            "padrão). Defina uma palavra-passe real no .env antes do primeiro arranque."
        )


def ensure_initial_data(db: Session) -> None:
    team_count = db.scalar(select(Team.id).limit(1))
    if team_count is None:
        _require_initial_password()
        db.add(
            Team(
                name=settings.initial_admin_name,
                user=User(
                    name=settings.initial_admin_name,
                    username=settings.initial_admin_username,
                    password_hash=hash_password(settings.initial_admin_password),
                    email=settings.initial_admin_email or None,
                    is_admin=True,
                    is_active=True,
                    can_request_pin=False,
                ),
                is_active=True,
            )
        )
        db.commit()

    defaults = [
        {
            "name": "Noite",
            "slug": "night",
            "schedule_type": "fixed",
            "weekdays": "0,1,2,3,4,5,6",
            "start_time": time(20, 30),
            "end_time": time(0, 0),
            "rotation_anchor_date": None,
        },
        {
            "name": "Almoço - Sábados",
            "slug": "saturday-lunch",
            "schedule_type": "rotation",
            "weekdays": "5",
            "start_time": time(13, 0),
            "end_time": time(16, 0),
            "rotation_anchor_date": date(2024, 1, 6),
        },
        {
            "name": "Almoço - Domingo",
            "slug": "sunday-lunch",
            "schedule_type": "rotation",
            "weekdays": "6",
            "start_time": time(13, 0),
            "end_time": time(16, 0),
            "rotation_anchor_date": date(2024, 1, 7),
        },
    ]

    for item in defaults:
        exists = db.scalar(select(Schedule.id).where(Schedule.slug == item["slug"]))
        if exists is None:
            db.add(Schedule(**item, requires_manager_approval=True, is_active=True))
    db.commit()
