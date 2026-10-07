import pytest


@pytest.mark.parametrize("payload", [None, {}, {"password": ""}, {"password": 123}])
def test_login_validation_error_shape(client, payload):
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 400
    assert response.json() == {"error": "Os dados enviados não são válidos."}


def test_login_limiter_cookie_and_logout(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": "test-password"}).status_code == 429
    response = client.post("/api/auth/logout")
    assert response.json() == {"authenticated": False}
    assert "Path=/jogo/" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_head_and_malformed_json_follow_api_contract(client):
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


def test_display_fallback_for_unknown_panel_and_fractional_sqlite_zoom(client):
    # SQLite INTEGER affinity permits fractional values within the BETWEEN check.
    with client.app.state.engine.begin() as connection:
        connection.exec_driver_sql("UPDATE display_settings SET active_panel='old-panel', zoom_percent=100.5")
    response = client.get("/api/public/state")
    assert response.status_code == 200
    assert response.json()["display"] == {"activePanel": "latest-results", "zoomPercent": 100}
