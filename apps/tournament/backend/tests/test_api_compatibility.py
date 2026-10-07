import json
from pathlib import Path
import shutil

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

FIXTURES = Path(__file__).resolve().parents[4] / "migration/fixtures"


def test_replays_saved_node_workflow_statuses_and_json(client):
    token = None
    for observation in json.loads((FIXTURES / "tournament-api.json").read_text()):
        request, expected = observation["request"], observation["response"]
        headers = {"cookie": token} if request["authorized"] and token else {}
        response = client.request(request["method"], request["url"], json=request.get("payload"), headers=headers)
        assert response.status_code == expected["status"], (request, response.text)
        assert response.json() == expected["body"], request
        if request["url"] == "/api/auth/login" and response.status_code == 200:
            token = f"tournament_admin_session={response.cookies['tournament_admin_session']}"


def test_python_startup_adopts_node_database_and_preserves_public_state(settings):
    shutil.copyfile(FIXTURES / "tournament.sqlite", settings.database_path)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/public/state")
        assert response.status_code == 200
        assert response.json() == json.loads((FIXTURES / "tournament-state.json").read_text())
    # The Node-era rows remain unchanged, including timestamps and sequence-backed IDs.
    import sqlite3
    with sqlite3.connect(settings.database_path) as db:
        db.row_factory = sqlite3.Row
        for table, rows in json.loads((FIXTURES / "tournament-rows.json").read_text()).items():
            assert [dict(row) for row in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid')] == rows


@pytest.mark.parametrize("payload", [None, {}, {"password": ""}, {"password": 123}])
def test_login_validation_error_shape(client, payload):
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 400
    assert response.json() == {"error": "Os dados enviados não são válidos."}


def test_login_limiter_cookie_and_logout(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": "migration-fixture-password"}).status_code == 429
    response = client.post("/api/auth/logout")
    assert response.json() == {"authenticated": False}
    assert "Path=/jogo/" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_head_and_malformed_json_follow_legacy_contract(client):
    response = client.head("/api/public/state")
    assert response.status_code == 200 and response.content == b""
    response = client.post("/api/auth/login", content="{", headers={"content-type": "application/json"})
    assert response.status_code == 500
    assert response.json() == {"error": "Ocorreu um erro inesperado. Tente novamente."}


@pytest.mark.parametrize("payload", [
    {"name": " ", "groupId": 1}, {"name": "T", "groupId": 1, "number": "1"},
    {"name": "T", "groupId": 1, "number": True}, {"name": "T", "groupId": 1, "number": 1.5},
])
def test_rejects_invalid_team_payloads(admin, payload):
    response = admin.post("/api/admin/teams", json=payload)
    assert response.status_code == 400


def test_all_saved_api_routes_exist_with_matching_methods(settings):
    app = create_app(settings)
    routes = {(method.upper(), path) for path, operations in app.openapi()["paths"].items() for method in operations}
    for expected in json.loads((FIXTURES / "tournament-routes.json").read_text()):
        import re
        path = re.sub(r":(\w+)", r"{\1}", expected["path"])
        assert (expected["method"], path) in routes
    app.state.engine.dispose()


def test_request_aliases_and_unicode_name_limits_follow_zod(admin):
    assert admin.put("/api/admin/display", json={"active_panel": "classification", "zoom_percent": 100}).status_code == 400
    assert admin.post("/api/admin/teams", json={"name": "T", "group_id": 1}).status_code == 400
    assert admin.post("/api/admin/teams", json={"name": "T", "groupId": 1, "number": None}).status_code == 400
    assert admin.post("/api/admin/teams", json={"name": "\U0001f600" * 101, "groupId": 1}).status_code == 400
    response = admin.post("/api/admin/teams", json={"name": "\ufeff Equipa \ufeff", "groupId": "0x1"})
    assert response.status_code == 201
    assert response.json()["name"] == "Equipa"


def test_concurrent_automatic_team_numbers_are_unique_and_contiguous(admin):
    from concurrent.futures import ThreadPoolExecutor
    def create(index):
        response = admin.post("/api/admin/teams", json={"name": f"Equipa {index}", "groupId": 1})
        assert response.status_code == 201
        return response.json()["number"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(create, range(4))) == [1, 2, 3, 4]


def test_legacy_display_fallback_for_unknown_panel_and_fractional_sqlite_zoom(client):
    # SQLite INTEGER affinity permits fractional values within the legacy BETWEEN check.
    with client.app.state.engine.begin() as connection:
        connection.exec_driver_sql("UPDATE display_settings SET active_panel='old-panel', zoom_percent=100.5")
    response = client.get("/api/public/state")
    assert response.status_code == 200
    assert response.json()["display"] == {"activePanel": "latest-results", "zoomPercent": 100}
