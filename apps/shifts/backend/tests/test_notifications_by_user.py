"""Notifications go to the user, never to the team.

Covers the recipient resolution in `services/notifications.py`, the admin and
self-service forms that keep the address, and the 0002 backfill that moved
existing data from `teams` onto `users`.
"""

import sqlite3
from datetime import datetime

from alembic import command
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import alembic_config
from app.models import NotificationLog, Team, User
from app.services.notifications import send_email_notification, send_many
from app.security import hash_password
from fastapi.testclient import TestClient

SMTP_UNSET = "SMTP_HOST não está configurado"


def _user(db: Session, username: str, email: str | None = None) -> User:
    user = User(
        name=username.capitalize(),
        username=username,
        password_hash=hash_password("secret123"),
        email=email,
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def _team(db: Session, name: str, user: User | None = None) -> Team:
    team = Team(name=name, user=user, phone=None, is_active=True)
    db.add(team)
    db.commit()
    return team


def _latest_log(db: Session) -> NotificationLog:
    return db.scalars(select(NotificationLog).order_by(NotificationLog.id.desc()).limit(1)).one()


def test_email_goes_to_the_user_behind_the_team(db: Session) -> None:
    """The recipient is the user's address; the log keeps both the user and the team."""
    user = _user(db, "alice", "alice@example.com")
    team = _team(db, "Equipa Alice", user)

    send_email_notification(db, team, "shift_reminder", "Assunto", "Corpo")

    log = _latest_log(db)
    assert log.user_id == user.id
    assert log.team_id == team.id
    assert log.recipient == "alice@example.com"
    assert log.status == "skipped" and log.error == SMTP_UNSET


def test_rota_only_team_logs_skipped_without_someone_to_write_to(db: Session) -> None:
    """A team without a user (and without an e-mail of its own) is recorded as skipped."""
    team = _team(db, "Só na escala")

    send_email_notification(db, team, "swap_requested", "Assunto", "Corpo")

    log = _latest_log(db)
    assert log.user_id is None and log.recipient is None
    assert log.status == "skipped"
    assert "não tem utilizador" in log.error


def test_send_many_sends_one_mail_per_user(db: Session) -> None:
    """Two teams of the same user are one recipient; a rota-only team still gets its row."""
    user = _user(db, "bruno", "bruno@example.com")
    first = _team(db, "Equipa B1", user)
    second = _team(db, "Equipa B2", user)
    rota_only = _team(db, "Só na escala")

    send_many(db, [first, second, rota_only], "swap_approved", "Assunto", "Corpo")

    logs = db.scalars(select(NotificationLog).order_by(NotificationLog.id)).all()
    assert len(logs) == 2  # one for the user, one for the rota-only team
    assert [log.recipient for log in logs] == ["bruno@example.com", None]


def test_admin_user_form_stores_and_refuses_email(db: Session, logged_in: TestClient) -> None:
    page = logged_in.get("/admin/users")
    token = page.text.split('name="csrf_token" value="')[1].split('"')[0]

    response = logged_in.post(
        "/admin/users",
        data={
            "name": "Carla",
            "username": "carla",
            "password": "secret123",
            "email": "  CARLA@EXAMPLE.COM ",
            "notify_email": "on",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    carla = db.scalar(select(User).where(User.username == "carla"))
    assert carla is not None
    assert carla.email == "carla@example.com" and carla.notify_email is True

    # The address is unique across users.
    response = logged_in.post(
        "/admin/users",
        data={
            "name": "Carla 2",
            "username": "carla2",
            "password": "secret123",
            "email": "carla@example.com",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db.scalar(select(User).where(User.username == "carla2")) is None


def test_admin_team_form_ignores_email_and_keeps_phone(
    db: Session, logged_in: TestClient
) -> None:
    """The team form no longer carries e-mail settings; a stray field is harmless."""
    page = logged_in.get("/admin/teams")
    token = page.text.split('name="csrf_token" value="')[1].split('"')[0]

    response = logged_in.post(
        "/admin/teams",
        data={
            "name": "Equipa Sem Correio",
            "phone": "912345678",
            "email": "orphan@example.com",
            "notify_email": "on",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    team = db.scalar(select(Team).where(Team.name == "Equipa Sem Correio"))
    assert team is not None
    assert team.phone == "912345678"
    assert not hasattr(team, "email") and not hasattr(team, "notify_email")


def test_account_page_is_the_self_service_for_the_address(
    db: Session, logged_in: TestClient, admin: User
) -> None:
    _user(db, "outro", "outro@example.com")
    page = logged_in.get("/account")
    token = page.text.split('name="csrf_token" value="')[1].split('"')[0]

    response = logged_in.post(
        "/account/email",
        data={"email": "  NOVO@EXAMPLE.COM ", "notify_email": "on", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db.refresh(admin)
    assert admin.email == "novo@example.com"

    # Someone else's address is refused, and the own address stays untouched.
    response = logged_in.post(
        "/account/email",
        data={"email": "outro@example.com", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db.refresh(admin)
    assert admin.email == "novo@example.com"


def test_0002_moves_addresses_from_teams_to_users(monkeypatch) -> None:
    """The migration backfills users.email and notification_logs.user_id and drops the team columns."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/migration.db"
        monkeypatch.setattr(settings, "database_url", url)
        cfg = alembic_config()

        command.upgrade(cfg, "0001_initial")
        path = Path(tmp) / "migration.db"
        conn = sqlite3.connect(path)
        now = datetime.now().isoformat(sep=" ")
        conn.executescript(
            f"""
            INSERT INTO users (id, name, username, password_hash, is_admin, is_active, created_at)
            VALUES (1, 'Alice', 'alice', 'x', 0, 1, '{now}'),
                   (2, 'Bruno', 'bruno', 'x', 0, 1, '{now}'),
                   (3, 'Carla', 'carla', 'x', 0, 1, '{now}');
            INSERT INTO teams (id, name, user_id, email, phone, calendar_token, is_active, notify_email, created_at)
            VALUES (1, 'Equipa A', 1, 'alice@example.com', NULL, NULL, 1, 1, '{now}'),
                   (2, 'Equipa B1', 2, 'bruno@example.com', NULL, NULL, 1, 0, '{now}'),
                   (3, 'Equipa B2', 2, 'bruno-2@example.com', NULL, NULL, 1, 0, '{now}'),
                   (4, 'Só na escala', NULL, 'orphan@example.com', NULL, NULL, 1, 1, '{now}');
            INSERT INTO notification_logs (id, team_id, event_type, channel, recipient, subject, body, status, created_at)
            VALUES (1, 1, 'shift_reminder', 'email', 'alice@example.com', 's', 'b', 'sent', '{now}'),
                   (2, 4, 'shift_reminder', 'email', 'orphan@example.com', 's', 'b', 'sent', '{now}'),
                   (3, NULL, 'shift_reminder', 'email', NULL, 's', 'b', 'skipped', '{now}');
            """
        )
        conn.commit()

        command.upgrade(cfg, "head")

        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        assert {"email", "notify_email"} <= columns
        teams_columns = {row[1] for row in conn.execute("PRAGMA table_info(teams)")}
        assert "email" not in teams_columns and "notify_email" not in teams_columns

        rows = conn.execute("SELECT username, email, notify_email FROM users ORDER BY id").fetchall()
        assert rows == [
            ("alice", "alice@example.com", 1),
            # Bruno's lowest-numbered team wins the shared account's address.
            ("bruno", "bruno@example.com", 0),
            # Carla's team had no address, so she has none either.
            ("carla", None, 1),
        ]
        logs = conn.execute("SELECT id, user_id FROM notification_logs ORDER BY id").fetchall()
        assert logs == [(1, 1), (2, None), (3, None)]  # the orphan team has no user to attribute

        command.downgrade(cfg, "0001_initial")
        teams_columns = {row[1] for row in conn.execute("PRAGMA table_info(teams)")}
        assert "email" in teams_columns and "notify_email" in teams_columns
        users_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        assert "email" not in users_columns and "notify_email" not in users_columns
        restored = conn.execute(
            "SELECT t.name, t.email, t.notify_email FROM teams t ORDER BY t.id"
        ).fetchall()
        assert restored == [
            ("Equipa A", "alice@example.com", 1),
            # Only Bruno's first team can take the unique team address back.
            ("Equipa B1", "bruno@example.com", 0),
            ("Equipa B2", None, 0),
            ("Só na escala", None, 1),
        ]
        logs_columns = {row[1] for row in conn.execute("PRAGMA table_info(notification_logs)")}
        assert "user_id" not in logs_columns
        conn.close()