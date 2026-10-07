from fastapi.testclient import TestClient

from app.main import create_app
from app.security.rate_limit import LoginRateLimiter
from app.security.session import create_token, valid_token


def test_session_matches_node_wire_format_and_rejects_expired_or_tampered_tokens(settings):
    # Produced by the frozen Node createSessionToken implementation at now=2000.
    token = "eyJleHBpcmVzQXQiOjYwNDgwMjAwMH0.MbES4fCzzaBuj5tLh_9osvDnYNwSKDYBlSYPpF-iJQo"
    assert create_token(settings, now=2000) == token
    assert valid_token(token, settings, now=2000)
    assert not valid_token(token, settings, now=604802000)
    assert not valid_token(token + "x", settings, now=2000)
    assert not valid_token(token + ".extra", settings)
    assert not valid_token("malformed", settings)


def test_limiter_expiry_ip_isolation_and_successful_login_reset(client):
    limiter = LoginRateLimiter()
    for _ in range(5):
        limiter.failure("a", now=1000)
    assert limiter.limited("a", now=1000)
    assert not limiter.limited("b", now=1000)
    assert not limiter.limited("a", now=901000)
    assert not limiter.attempts
    for _ in range(4):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": "migration-fixture-password"}).status_code == 200
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 429


def test_cookie_https_and_proxy_trust(settings):
    for trust, secure in [(False, False), (True, True)]:
        with TestClient(create_app(settings.model_copy(update={"trust_proxy": trust}))) as client:
            response = client.post("/api/auth/login", json={"password": "migration-fixture-password"},
                                   headers={"x-forwarded-proto": "https"})
            cookie = response.headers["set-cookie"]
            assert ("; Secure" in cookie) is secure
            assert "HttpOnly" in cookie and "SameSite=strict" in cookie
            assert "Max-Age=604800" in cookie and "Path=/jogo/" in cookie
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.post("/api/auth/login", json={"password": "migration-fixture-password"})
        assert "; Secure" in response.headers["set-cookie"]


def test_parallel_failed_logins_do_not_bypass_five_attempt_limit(client):
    from collections import Counter
    from concurrent.futures import ThreadPoolExecutor
    def attempt(_index):
        return client.post("/api/auth/login", json={"password": "wrong"}).status_code
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert Counter(pool.map(attempt, range(6))) == {401: 5, 429: 1}
