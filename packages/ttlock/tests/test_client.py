import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from urllib.parse import parse_qs

import httpx
import pytest

from ttlock import TTLockClient, TTLockConfig, TTLockError

CONFIG = TTLockConfig(client_id="client", client_secret="secret", username="owner", password="password", lock_id="123")


def generate(api):
    return api.generate_timed_pin(keyboard_pwd_name="test")


def test_oauth_cache_and_password_encoding():
    calls = []
    def handler(request):
        calls.append(request)
        payload = parse_qs(request.content.decode())
        if request.url.path == "/oauth2/token":
            assert payload["password"] == ["5f4dcc3b5aa765d61d8327deb882cf99"]
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        assert request.method == "GET"
        assert request.url.path == "/v3/lock/listKeyboardPwd"
        return httpx.Response(200, json={"list": [], "pages": 1})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = TTLockClient(CONFIG, client=http)
        for _ in range(2):
            api.list_passcodes()
    assert len(calls) == 3


@pytest.mark.parametrize("response", ["timeout", "malformed", "missing_id", "rejected", "http_error", "unknown_error"])
def test_cloud_failure_classification_and_no_secret_in_errors(response):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        if response == "timeout":
            raise httpx.ReadTimeout("secret-code", request=request)
        if response == "malformed":
            return httpx.Response(200, text="secret-code")
        if response == "missing_id":
            return httpx.Response(200, json={"secret": "secret-code"})
        if response == "http_error":
            return httpx.Response(500, text="secret-code")
        return httpx.Response(200, json={"errcode": -3009 if response == "rejected" else "secret-code", "errmsg": "secret-code"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TTLockError) as failure:
            generate(TTLockClient(CONFIG, client=http))
    assert failure.value.uncertain == (response != "rejected")
    assert "secret-code" not in str(failure.value)
    assert calls == ["/oauth2/token", "/v3/keyboardPwd/get"]


def test_expired_token_refreshes_once():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        if len(calls) == 2:
            return httpx.Response(200, json={"errcode": 10004})
        return httpx.Response(200, json={"keyboardPwdId": 42, "keyboardPwd": "123456789"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert generate(TTLockClient(CONFIG, client=http))["keyboardPwdId"] == 42
    assert calls == ["/oauth2/token", "/v3/keyboardPwd/get", "/oauth2/token", "/v3/keyboardPwd/get"]


def test_expired_token_does_not_loop():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(200, json={"errcode": 10004})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TTLockError, match="api_10004"):
            generate(TTLockClient(CONFIG, client=http))
    assert len(calls) == 4


def test_http_client_logs_do_not_leak_tokens(caplog):
    def handler(request):
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "private-token", "expires_in": 3600})
        return httpx.Response(200, json={"list": [], "pages": 1})
    with caplog.at_level(logging.INFO, logger="httpx"):
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            assert TTLockClient(CONFIG, client=http).list_passcodes() == []
    assert "private-token" not in caplog.text


@pytest.mark.parametrize("method,path", [("list_locks", "/v3/lock/list"), ("list_passcodes", "/v3/lock/listKeyboardPwd")])
def test_paginated_lists(method, path):
    pages = []
    def handler(request):
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        if request.url.path == "/v3/key/list":
            return httpx.Response(200, json={"list": [], "pages": 1})
        assert request.url.path == path
        assert request.url.params["pageSize"] == "200"
        if method == "list_passcodes":
            assert request.url.params["lockId"] == "123"
            assert request.url.params["orderBy"] == "1"
        page = int(request.url.params["pageNo"])
        pages.append(page)
        return httpx.Response(200, json={"list": [{"lockId": page}], "pages": 2})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = TTLockClient(CONFIG, client=http)
        result = api.list_locks() if method == "list_locks" else api.list_passcodes()
    assert result == [{"lockId": 1}, {"lockId": 2}]
    assert pages == [1, 2]


def test_shared_locks_are_discovered_and_deduplicated_with_permissions():
    calls = []
    owned = [{"lockId": 123, "lockName": "Owned door", "hasGateway": 1}]
    keys = [
        {"lockId": "123", "lockName": "eKey name", "keyId": 1, "userType": "110301", "keyRight": 1},
        {"lockId": 456, "lockName": "Shared door", "keyId": 2, "userType": "110302", "keyRight": 1,
         "remoteEnable": 1, "keyStatus": "110401", "startDate": 1000, "endDate": 2000},
        {"lockId": "456", "lockName": "Shared door", "keyId": 2, "userType": "110302", "keyRight": 1},
    ]
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(200, json={"list": owned if request.url.path == "/v3/lock/list" else keys, "pages": 1})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = TTLockClient(CONFIG, client=http).list_locks()
    assert len(result) == 2
    assert result[0] == {**owned[0], "keyId": 1, "userType": "110301", "keyRight": 1}
    assert result[1] == keys[1]
    assert calls == ["/oauth2/token", "/v3/lock/list", "/v3/key/list"]


@pytest.mark.parametrize("owned,keys", [([], []), ([{"lockId": 123}], []),
                                      ([], [{"lockId": 456, "userType": "110302", "keyRight": 0}])])
def test_owned_only_shared_only_and_empty_lock_lists(owned, keys):
    def handler(request):
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(200, json={"list": owned if request.url.path == "/v3/lock/list" else keys, "pages": 1})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert TTLockClient(CONFIG, client=http).list_locks() == owned + keys


def test_shared_ekeys_are_paginated():
    pages = []
    def handler(request):
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        if request.url.path == "/v3/lock/list":
            return httpx.Response(200, json={"list": [], "pages": 1})
        assert request.url.path == "/v3/key/list"
        page = int(request.url.params["pageNo"])
        pages.append(page)
        return httpx.Response(200, json={"list": [{"lockId": page, "keyRight": 1}], "pages": 2})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = TTLockClient(CONFIG, client=http).list_locks()
    assert result == [{"lockId": 1, "keyRight": 1}, {"lockId": 2, "keyRight": 1}]
    assert pages == [1, 2]


def test_ekey_failure_is_not_reported_as_an_empty_or_partial_list():
    def handler(request):
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        if request.url.path == "/v3/lock/list":
            return httpx.Response(200, json={"list": [{"lockId": 123}], "pages": 1})
        return httpx.Response(200, json={"errcode": -1003, "errmsg": "private-provider-message"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TTLockError, match="api_-1003"):
            TTLockClient(CONFIG, client=http).list_locks()


@pytest.mark.parametrize("record", [{}, {"lockId": "bad"}, {"lockId": 0}])
def test_invalid_ekey_lock_ids_are_sanitized(record):
    def handler(request):
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(200, json={"list": [] if request.url.path == "/v3/lock/list" else [record], "pages": 1})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TTLockError, match="invalid_list_response"):
            TTLockClient(CONFIG, client=http).list_locks()


@pytest.mark.parametrize("body", [{}, {"list": "secret"}, {"list": [], "pages": "bad"}, {"list": []}])
def test_invalid_list_response(body):
    def handler(request):
        return httpx.Response(200, json={"access_token": "token", "expires_in": 3600} if request.url.path == "/oauth2/token" else body)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TTLockError, match="invalid_list_response"):
            TTLockClient(CONFIG, client=http).list_locks()


def test_pagination_is_bounded():
    def handler(request):
        return httpx.Response(200, json={"access_token": "token", "expires_in": 3600} if request.url.path == "/oauth2/token" else {"list": [], "pages": 101})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TTLockError, match="too_many_pages"):
            TTLockClient(CONFIG, client=http).list_locks()


def test_live_config_invalidates_token_cache():
    config = CONFIG
    tokens = []
    def handler(request):
        if request.url.path == "/oauth2/token":
            tokens.append(request.content)
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(200, json={"list": [], "pages": 1})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = TTLockClient(lambda: config, client=http)
        api.list_locks()
        api.list_locks()
        config = replace(CONFIG, password="updated")
        api.list_locks()
    assert len(tokens) == 2
    assert tokens[0] != tokens[1]


def test_token_expires_with_safety_margin(monkeypatch):
    clock = 100.0
    monkeypatch.setattr("ttlock.client.time.monotonic", lambda: clock)
    tokens = []
    def handler(request):
        if request.url.path == "/oauth2/token":
            tokens.append(request)
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(200, json={"list": [], "pages": 1})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = TTLockClient(CONFIG, client=http)
        api.list_locks()
        clock = 3639.0
        api.list_locks()
        assert len(tokens) == 1
        clock = 3640.0
        api.list_locks()
    assert len(tokens) == 2


def test_concurrent_calls_share_token():
    tokens = []
    def handler(request):
        if request.url.path == "/oauth2/token":
            tokens.append(request)
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(200, json={"list": [], "pages": 1})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = TTLockClient(CONFIG, client=http)
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert list(pool.map(lambda _: api.list_locks(), range(8))) == [[]] * 8
    assert len(tokens) == 1


def test_redirects_are_not_followed_even_with_injected_client():
    calls = []
    def handler(request):
        calls.append(request.url)
        return httpx.Response(307, headers={"Location": "https://other.example.com"})
    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as http:
        with pytest.raises(TTLockError, match="invalid_response"):
            TTLockClient(CONFIG, client=http).list_locks()
    assert len(calls) == 1


@pytest.mark.parametrize("body", [{}, {"access_token": "token", "expires_in": 0}, {"access_token": 3, "expires_in": 3600}])
def test_invalid_oauth_response(body):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as http:
        with pytest.raises(TTLockError, match="invalid_token_response") as failure:
            generate(TTLockClient(CONFIG, client=http))
    assert not failure.value.uncertain


def test_config_env_and_secret_repr(monkeypatch):
    for key, value in {"CLIENT_ID": "client", "CLIENT_SECRET": "secret", "USERNAME": "owner", "PASSWORD": "password", "API_BASE_URL": CONFIG.api_base_url, "LOCK_ID": "123"}.items():
        monkeypatch.setenv(f"TTLOCK_{key}", value)
    assert TTLockConfig.from_env() == CONFIG
    assert "secret" not in repr(CONFIG).replace("client_secret", "")
    assert "password='password'" not in repr(CONFIG)


@pytest.mark.parametrize("url", ["http://example.com", "https://user:secret@example.com", "https://example.com?secret=1", "https://example.com/path"])
def test_unsafe_configuration_never_calls_http(url):
    def handler(request):
        pytest.fail("Invalid configuration must not make requests")
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TTLockError, match="invalid_configuration"):
            TTLockClient(replace(CONFIG, api_base_url=url), client=http).list_locks()


def test_missing_credentials_never_calls_http():
    def handler(request):
        pytest.fail("Missing credentials must not make requests")
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TTLockError, match="invalid_configuration"):
            TTLockClient(TTLockConfig(), client=http).list_locks()


@pytest.mark.parametrize("lock_id", ["", "0", "-1", "not-a-lock", "١٢٣"])
@pytest.mark.parametrize("operation", ["list_passcodes", "generate_timed_pin", "generate_one_time_pin"])
def test_missing_or_invalid_bound_lock_never_calls_http(lock_id, operation):
    def handler(request):
        pytest.fail("Invalid bound lock must not make requests")
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = TTLockClient(replace(CONFIG, lock_id=lock_id), client=http)
        with pytest.raises(TTLockError, match="invalid_configuration"):
            if operation == "list_passcodes":
                api.list_passcodes()
            else:
                getattr(api, operation)(keyboard_pwd_name="test")


def test_discovery_does_not_require_bound_lock():
    def handler(request):
        return httpx.Response(200, json={"access_token": "token", "expires_in": 3600} if request.url.path == "/oauth2/token" else {"list": [], "pages": 1})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert TTLockClient(replace(CONFIG, lock_id=""), client=http).list_locks() == []


def test_bound_lock_and_credentials_are_snapshotted_for_each_operation():
    config = CONFIG
    def handler(request):
        nonlocal config
        if request.url.path == "/oauth2/token":
            config = replace(CONFIG, lock_id="456", client_id="other-client")
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        assert request.url.params["lockId"] == "123"
        assert request.url.params["clientId"] == "client"
        return httpx.Response(200, json={"list": [], "pages": 1})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert TTLockClient(lambda: config, client=http).list_passcodes() == []
