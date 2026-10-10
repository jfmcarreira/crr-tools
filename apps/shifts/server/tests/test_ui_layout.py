"""Keep browser presentation separate without changing its public routes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import UI_DIR, app


def test_ui_is_outside_the_python_application() -> None:
    shifts_dir = Path(__file__).resolve().parents[2]
    assert UI_DIR == shifts_dir / "ui"
    assert (UI_DIR / "templates").is_dir()
    assert (UI_DIR / "static").is_dir()
    assert not (shifts_dir / "server" / "app" / "templates").exists()
    assert not (shifts_dir / "server" / "app" / "static").exists()


@pytest.mark.parametrize("prefix", ["", "/crr"])
def test_service_worker_is_served_from_ui_at_app_root(db: Session, prefix: str) -> None:
    with TestClient(app, root_path=prefix) as client:
        response = client.get(f"{prefix}/sw.js")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/javascript")
        assert response.headers["cache-control"] == "no-cache"
        assert response.content == (UI_DIR / "static" / "sw.js").read_bytes()
