"""Verify the service worker's public route and deployment-prefix support."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import UI_DIR, app


@pytest.mark.parametrize("prefix", ["", "/crr"])
def test_service_worker_is_served_from_ui_at_app_root(db: Session, prefix: str) -> None:
    with TestClient(app, root_path=prefix) as client:
        response = client.get(f"{prefix}/sw.js")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/javascript")
        assert response.headers["cache-control"] == "no-cache"
        assert response.content == (UI_DIR / "static" / "sw.js").read_bytes()
