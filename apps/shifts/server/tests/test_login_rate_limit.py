"""Brute-force protection on /login."""

from fastapi.testclient import TestClient

RATE_MESSAGE = "Demasiadas tentativas de início de sessão"


def _attempt(client: TestClient, username: str, password: str):
    page = client.get("/login")
    token = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token},
        follow_redirects=True,
    )


def test_lockout_after_repeated_failures(client: TestClient, admin) -> None:
    for _ in range(5):
        response = _attempt(client, admin.username, "wrong-password")
        assert RATE_MESSAGE not in response.text

    # The sixth attempt is refused even with the correct password.
    response = _attempt(client, admin.username, "secret123")
    assert RATE_MESSAGE in response.text
    assert client.get("/account").status_code == 401


def test_other_accounts_are_not_affected(client: TestClient, admin) -> None:
    for _ in range(5):
        _attempt(client, "nobody", "wrong-password")

    response = _attempt(client, admin.username, "secret123")
    assert RATE_MESSAGE not in response.text
    assert client.get("/account").status_code == 200


def test_successful_login_resets_the_counter(client: TestClient, admin) -> None:
    for _ in range(4):
        _attempt(client, admin.username, "wrong-password")

    assert RATE_MESSAGE not in _attempt(client, admin.username, "secret123").text

    for _ in range(4):
        _attempt(client, admin.username, "wrong-password")

    # Four more failures after a success: still under the limit.
    assert RATE_MESSAGE not in _attempt(client, admin.username, "wrong-password").text
