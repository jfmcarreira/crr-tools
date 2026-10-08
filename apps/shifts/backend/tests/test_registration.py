import pytest
from sqlalchemy import select

from app.config import Settings, settings
from app.main import app
from app.models import Team, User
from app.security import verify_password
from app.security.rate_limit import LoginRateLimiter


@pytest.fixture(autouse=True)
def registration(monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", True)
    monkeypatch.setattr(app.state, "registration_limiter", LoginRateLimiter(5, 300))


def submit(client, **values):
    # Step 1: team validation
    page = client.get("/register")
    token = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    team_name = values.pop("team_name", "Equipa Norte")
    username = values.pop("username", "new-user")
    password = values.pop("password", "secret123")
    resp = client.post("/register", data={
        "csrf_token": token, "step": "team", "team_name": team_name,
    }, follow_redirects=False)
    # If redirected (error) return it
    if resp.status_code != 200:
        return resp
    # Step 2
    token2 = resp.text.split('name="csrf_token" value="')[1].split('"')[0]
    data = {
        "csrf_token": values.pop("csrf_token", token2),
        "step": "user",
        "team_name": team_name,
        "username": username,
        "password": password,
    }
    for k, v in values.items():
        data[k] = v
    return client.post("/register", data=data, follow_redirects=False)


def test_disabled_redirects_and_hides_link(client, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", False)
    for response in (client.get("/register", follow_redirects=False),
                     client.post("/register", follow_redirects=False)):
        assert response.status_code == 303
        assert response.headers["location"] == "/"
    assert 'href="/register"' not in client.get("/login").text


def test_env_toggle(monkeypatch):
    monkeypatch.setenv("REGISTRATION_ENABLED", "true")
    assert Settings(_env_file=None).registration_enabled is True
    monkeypatch.setenv("REGISTRATION_ENABLED", "false")
    assert Settings(_env_file=None).registration_enabled is False


def test_register_claims_team_and_signs_in(client, db, team):
    team.name = "Equipa Contínuos"
    db.commit()
    response = submit(client, team_name="  EQUIPA CONTÍNUOS  ", username=" New-User ",
                      name=" Novo utilizador ", is_admin="true")
    assert response.headers["location"] == "/"
    user = db.scalar(select(User).where(User.username == "new-user"))
    assert user and user.is_active and not user.is_admin
    assert user.name == team.name
    assert verify_password("secret123", user.password_hash)
    db.refresh(team)
    assert team.user_id == user.id
    assert "Conta criada com sucesso." in client.get("/").text
    assert client.get("/account").status_code == 200
    assert client.get("/admin/users").status_code == 403


@pytest.mark.parametrize("state", ["missing", "assigned", "inactive", "ambiguous"])
def test_unavailable_team_creates_no_account(client, db, team, admin, state):
    if state == "missing":
        team.name = "Outra equipa"
    elif state == "assigned":
        team.user_id = admin.id
    elif state == "inactive":
        team.is_active = False
    else:
        db.add(Team(name="EQUIPA NORTE"))
    db.commit()
    response = submit(client)
    assert response.headers["location"] == "/register"
    assert db.scalar(select(User).where(User.username == "new-user")) is None
    db.refresh(team)
    assert team.user_id == (admin.id if state == "assigned" else None)


@pytest.mark.parametrize("values", [
    {"username": "TEST-ADMIN"}, {"username": "bad user"}, {"password": "a"},
    {"username": ""}, {"username": "x" * 81},
])
def test_invalid_input(client, db, team, values):
    res = submit(client, **values)
    assert res.headers["location"] == "/register"
    assert db.scalar(select(User).where(User.username == "new-user")) is None
    db.refresh(team)
    assert team.user_id is None


def test_csrf_rejected(client, db, team):
    assert submit(client, csrf_token="invalid").status_code == 400
    assert db.scalar(select(User).where(User.username == "new-user")) is None


def test_rate_limit_counts_different_names_and_expires(client, db, team, monkeypatch):
    limiter = app.state.registration_limiter
    monkeypatch.setattr(limiter, "_now", lambda: 1000)
    for index in range(5):
        assert submit(client, username=f"guess-{index}", password="a").headers["location"] == "/register"
    response = submit(client)
    assert response.headers["location"] == "/register"
    assert "Demasiadas tentativas de registo." in client.get("/register").text
    assert db.scalar(select(User).where(User.username == "new-user")) is None
    monkeypatch.setattr(limiter, "_now", lambda: 301000)
    assert submit(client).headers["location"] == "/"


def test_success_does_not_reset_limit(client, team):
    assert submit(client).headers["location"] == "/"
    assert app.state.registration_limiter.attempts["testclient"][0] == 1


def test_team_step_only_validates(client, db, team):
    page = client.get("/register")
    assert 'name="username"' not in page.text
    token = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    response = client.post("/register", data={
        "csrf_token": token, "step": "team", "team_name": team.name,
    })
    assert response.status_code == 200
    assert 'name="username"' in response.text
    assert 'name="password"' in response.text
    assert app.state.registration_limiter.attempts == {}
    assert db.scalar(select(User).where(User.username == "new-user")) is None
    db.refresh(team)
    assert team.user_id is None


def test_team_is_revalidated_on_user_step(client, db, team, admin):
    page = client.get("/register")
    token = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    response = client.post("/register", data={
        "csrf_token": token, "step": "team", "team_name": team.name,
    })
    token = response.text.split('name="csrf_token" value="')[1].split('"')[0]
    team.user_id = admin.id
    db.commit()
    response = client.post("/register", data={
        "csrf_token": token, "step": "user", "team_name": team.name,
        "username": "new-user", "password": "secret123",
    }, follow_redirects=False)
    assert response.headers["location"] == "/register"
    assert db.scalar(select(User).where(User.username == "new-user")) is None
    db.refresh(team)
    assert team.user_id == admin.id


def test_subpath_links_and_redirects(client, monkeypatch):
    monkeypatch.setattr(settings, "root_path", "/crr")
    assert 'action="/crr/register"' in client.get("/register").text
    assert 'href="/crr/register"' in client.get("/login").text
    monkeypatch.setattr(settings, "registration_enabled", False)
    assert client.post("/register", follow_redirects=False).headers["location"] == "/crr/"
    assert client.get("/register", follow_redirects=False).headers["location"] == "/crr/"


def test_logged_in_registration_redirects(logged_in):
    assert logged_in.get("/register", follow_redirects=False).headers["location"] == "/"
    assert logged_in.post("/register", follow_redirects=False).headers["location"] == "/"
