import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(admin_password="test-password", session_secret="test-secret-not-for-production-0000",
                    database_path=str(tmp_path / "tournament.sqlite"), app_base_path="/jogo/")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def admin(client):
    response = client.post("/api/auth/login", json={"password": "test-password"})
    assert response.status_code == 200
    client.headers["cookie"] = f"tournament_admin_session={response.cookies['tournament_admin_session']}"
    return client
