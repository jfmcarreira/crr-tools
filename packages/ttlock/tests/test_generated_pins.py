from datetime import datetime, timedelta, timezone

import httpx
import pytest

from ttlock import TTLockClient, TTLockConfig, TTLockError

CONFIG = TTLockConfig(client_id="client", client_secret="secret", username="owner", password="password", lock_id="123")
START = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return START + timedelta(minutes=50)
    monkeypatch.setattr("ttlock.client.datetime", Clock)


def generate(api, single_use, **kwargs):
    method = api.generate_one_time_pin if single_use else api.generate_timed_pin
    return method(keyboard_pwd_name="test", **kwargs)


@pytest.mark.parametrize("single_use", [False, True])
def test_generated_pin_payload_and_oauth_cache(single_use):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        assert request.method == "GET"
        assert request.url.path == "/v3/keyboardPwd/get"
        params = request.url.params
        assert params["lockId"] == "123"
        assert params["keyboardPwdName"] == "test"
        assert params["keyboardPwdVersion"] == "4"
        assert params["keyboardPwdType"] == ("1" if single_use else "3")
        assert params["startDate"] == str(int(START.timestamp() * 1000))
        assert params["accessToken"] == "token"
        assert "date" in params
        assert "addType" not in params
        assert "keyboardPwd" not in params
        if single_use:
            assert "endDate" not in params
        else:
            assert params["endDate"] == str(int((START + timedelta(hours=2)).timestamp() * 1000))
        return httpx.Response(200, json={"keyboardPwdId": "42", "keyboardPwd": "012345678"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = TTLockClient(CONFIG, client=http)
        for _ in range(2):
            result = generate(api, single_use)
            assert result == {"keyboardPwdId": "42", "keyboardPwd": "012345678", "lockId": "123",
                              "startDate": int(START.timestamp() * 1000),
                              "endDate": int((START + timedelta(hours=6 if single_use else 2)).timestamp() * 1000)}
    assert calls == ["/oauth2/token", "/v3/keyboardPwd/get", "/v3/keyboardPwd/get"]


@pytest.mark.parametrize("now", [
    START, START + timedelta(minutes=59, seconds=59),
    datetime(2026, 10, 10, 23, 59, 59, tzinfo=timezone.utc),
    datetime(2026, 12, 31, 23, 50, tzinfo=timezone.utc),
])
def test_timed_window_is_fixed_to_current_and_next_hour(monkeypatch, now):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    monkeypatch.setattr("ttlock.client.datetime", Clock)
    expected_start = now.replace(minute=0, second=0, microsecond=0)
    def handler(request):
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        assert int(request.url.params["startDate"]) == int(expected_start.timestamp() * 1000)
        assert int(request.url.params["endDate"]) == int((expected_start + timedelta(hours=2)).timestamp() * 1000)
        return httpx.Response(200, json={"keyboardPwdId": 42, "keyboardPwd": "123456789"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        generate(TTLockClient(CONFIG, client=http), False)


@pytest.mark.parametrize("single_use", [False, True])
def test_invalid_version_fails_before_http(single_use):
    def handler(request):
        pytest.fail("Invalid generation inputs must not make requests")
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ValueError):
            generate(TTLockClient(CONFIG, client=http), single_use, keyboard_pwd_version=5)


@pytest.mark.parametrize("single_use", [False, True])
@pytest.mark.parametrize("response", ["timeout", "malformed", "missing_code", "missing_id", "bad_code", "http_error"])
def test_generation_failure_is_sanitized_uncertain_and_not_retried(single_use, response):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        if response == "timeout":
            raise httpx.ReadTimeout("private-secret", request=request)
        if response == "malformed":
            return httpx.Response(200, text="private-secret")
        if response == "http_error":
            return httpx.Response(500, text="private-secret")
        body = {"keyboardPwdId": 42, "keyboardPwd": "123456789"}
        if response == "missing_code":
            del body["keyboardPwd"]
        elif response == "missing_id":
            del body["keyboardPwdId"]
        else:
            body["keyboardPwd"] = "private-secret"
        return httpx.Response(200, json=body)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TTLockError) as failure:
            generate(TTLockClient(CONFIG, client=http), single_use)
    assert failure.value.uncertain
    assert failure.value.start_date == int(START.timestamp() * 1000)
    assert failure.value.end_date == int((START + timedelta(hours=6 if single_use else 2)).timestamp() * 1000)
    assert "private-secret" not in str(failure.value)
    assert calls == ["/oauth2/token", "/v3/keyboardPwd/get"]


def test_generation_refreshes_expired_token_once():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        if len(calls) == 2:
            return httpx.Response(200, json={"errcode": 10004})
        return httpx.Response(200, json={"keyboardPwdId": 42, "keyboardPwd": "123456789"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        generate(TTLockClient(CONFIG, client=http), True)
    assert calls == ["/oauth2/token", "/v3/keyboardPwd/get", "/oauth2/token", "/v3/keyboardPwd/get"]


def test_crossing_hour_boundary_does_not_change_requested_or_reported_window(monkeypatch):
    times = iter([START + timedelta(minutes=59, seconds=59), START + timedelta(hours=1)])
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(times)
    monkeypatch.setattr("ttlock.client.datetime", Clock)
    def handler(request):
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        assert int(request.url.params["startDate"]) == int(START.timestamp() * 1000)
        assert int(request.url.params["endDate"]) == int((START + timedelta(hours=2)).timestamp() * 1000)
        return httpx.Response(200, json={"keyboardPwdId": 42, "keyboardPwd": "123456789"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = generate(TTLockClient(CONFIG, client=http), False)
    assert result["startDate"] == int(START.timestamp() * 1000)
    assert result["endDate"] == int((START + timedelta(hours=2)).timestamp() * 1000)


@pytest.mark.parametrize("kwargs", [{"lock_id": "456"}, {"start_at_utc": START},
                                    {"end_at_utc": START + timedelta(hours=3)}])
def test_generated_timed_pin_cannot_override_bound_lock_or_fixed_window(kwargs):
    with pytest.raises(TypeError):
        generate(TTLockClient(CONFIG), False, **kwargs)
