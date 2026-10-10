import os
import re
from collections.abc import Iterator
from datetime import date
from tempfile import TemporaryDirectory

# Settings and the engine are built at import time, so the environment has to be
# set before any app module is imported: a temporary database and no real SMTP.
_TMP = TemporaryDirectory(prefix="crr-export-tests-")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_TMP.name}/test.db",
    "BACKUP_DIR": f"{_TMP.name}/backups",
    "SECRET_KEY": "test-secret-key-for-unit-tests-only-0123456789",
    "APP_NAME": "Contínuos CRR",
    "BASE_URL": "http://testserver",
    "CALENDAR_TOKEN": "",
    "TIMEZONE": "Europe/Lisbon",
    "TRUSTED_PROXY_HOSTS": "*",
    "SMTP_HOST": "",
    "SMTP_USERNAME": "",
    "SMTP_PASSWORD": "",
    "SMTP_PORT": "587",
    "SMTP_FROM": "test@example.com",
    "SMTP_STARTTLS": "false",
    "VAPID_PUBLIC_KEY": "",
    "VAPID_PRIVATE_KEY": "",
    "VAPID_SUBJECT": "",
    "REMINDER_DAYS_AHEAD": "1",
    "ROOT_PATH": "",
    "SESSION_HTTPS_ONLY": "false",
    "INITIAL_ADMIN_USERNAME": "test-admin",
    "INITIAL_ADMIN_PASSWORD": "secret123",
    "INITIAL_ADMIN_NAME": "Administrador de teste",
    "INITIAL_ADMIN_EMAIL": "admin@example.com",
})

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.services.bootstrap import ensure_initial_data
from app.database import Base, SessionLocal, engine, run_migrations
from app.main import app
from app.models import Schedule, Team, User
from app.security import hash_password
from app.security.rate_limit import LoginRateLimiter


def sign_in(client: TestClient, username: str, password: str) -> TestClient:
    page = client.get("/login")
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match, "the login form should carry a CSRF token"
    client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": match.group(1)},
        follow_redirects=True,
    )
    return client


@pytest.fixture
def db() -> Iterator[Session]:
    # The Alembic stamp has to go too, or `upgrade` finds nothing left to do.
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    run_migrations()
    with SessionLocal() as session:
        ensure_initial_data(session)
        yield session


@pytest.fixture(scope="session", autouse=True)
def cleanup_database() -> Iterator[None]:
    yield
    engine.dispose()
    _TMP.cleanup()


@pytest.fixture(autouse=True)
def isolate_background_cleanup(monkeypatch):
    # Production's clock must not expire fixtures using a fixed synthetic date.
    from app.services import access_cleanup
    monkeypatch.setattr(access_cleanup, "_clear_expired_pins", lambda: None)


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> Iterator[None]:
    """Failed logins accumulate on the shared app; start every test fresh."""
    app.state.limiter = LoginRateLimiter()
    yield


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin(db: Session) -> User:
    """The administrator the app lifespan bootstraps, with a known password."""
    user = db.scalar(select(User).where(User.username == settings.initial_admin_username))
    assert user is not None
    user.password_hash = hash_password("secret123")
    db.commit()
    return user


@pytest.fixture
def logged_in(client: TestClient, admin: User) -> TestClient:
    return sign_in(client, admin.username, "secret123")


@pytest.fixture
def schedule(db: Session) -> Schedule:
    row = Schedule(
        name="Almoço de sábado",
        slug="almoco-sabado",
        schedule_type="rotation",
        weekdays="5",
        rotation_anchor_date=date(2026, 1, 3),
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def team(db: Session) -> Team:
    row = Team(name="Equipa Norte")
    db.add(row)
    db.commit()
    return row
