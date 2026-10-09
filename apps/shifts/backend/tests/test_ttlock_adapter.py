from unittest.mock import Mock

import pytest

from app.config import settings
from app.services import ttlock
from ttlock import TTLockClient, TTLockError


def test_shim_resolves_live_settings(monkeypatch):
    for name, value in {"ttlock_client_secret": "secret", "ttlock_username": "owner",
                        "ttlock_password": "password", "ttlock_api_base_url": "https://euopen.ttlock.com"}.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(settings, "ttlock_client_id", "first")
    client = ttlock.TTLockClient()
    assert isinstance(client, TTLockClient)
    assert client._resolve_config().client_id == "first"
    monkeypatch.setattr(settings, "ttlock_client_id", "second")
    assert client._resolve_config().client_id == "second"


def test_shim_generates_period_codes_with_feature_flag_and_bound_lock(monkeypatch):
    for name, value in {"ttlock_lock_id": "123", "ttlock_client_id": "client",
                        "ttlock_client_secret": "secret", "ttlock_username": "owner",
                        "ttlock_password": "password", "ttlock_api_base_url": "https://euopen.ttlock.com"}.items():
        monkeypatch.setattr(settings, name, value)
    create = Mock(return_value={"keyboardPwdId": 42, "keyboardPwd": "012345678"})
    monkeypatch.setattr(ttlock.ttlock_client, "generate_timed_pin", create)
    kwargs = dict(lock_id="123", name="test")
    monkeypatch.setattr(settings, "ttlock_enabled", False)
    with pytest.raises(TTLockError, match="disabled"):
        ttlock.issue_pin_via_ttlock(**kwargs)
    create.assert_not_called()
    monkeypatch.setattr(settings, "ttlock_enabled", True)
    assert ttlock.issue_pin_via_ttlock(**kwargs) == {"keyboardPwdId": 42, "keyboardPwd": "012345678"}
    create.assert_called_once_with(keyboard_pwd_name="test")
    create.reset_mock()
    with pytest.raises(TTLockError, match="lock_mismatch"):
        ttlock.issue_pin_via_ttlock(**{**kwargs, "lock_id": "456"})
    create.assert_not_called()


def test_shim_never_reconciles_a_different_lock(monkeypatch):
    for name, value in {"ttlock_lock_id": "123", "ttlock_client_id": "client",
                        "ttlock_client_secret": "secret", "ttlock_username": "owner",
                        "ttlock_password": "password", "ttlock_api_base_url": "https://euopen.ttlock.com"}.items():
        monkeypatch.setattr(settings, name, value)
    with pytest.raises(TTLockError, match="lock_mismatch"):
        ttlock.TTLockClient().list_passcodes("456")
