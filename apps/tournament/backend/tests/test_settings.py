from pathlib import Path

from app.config import Settings


def test_default_env_file_is_at_repository_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert Settings.model_config["env_file"] == Path(__file__).resolve().parents[4] / ".env"


def test_shared_env_file_ignores_other_app_keys_and_environment_wins(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ADMIN_PASSWORD=file-password\nSESSION_SECRET=" + "t" * 32 + "\n"
        "SECRET_KEY=" + "s" * 32 + "\nAPP_NAME=Contínuos de teste\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.chdir(tmp_path.parent)
    assert Settings(_env_file=env_file).admin_password == "file-password"
    monkeypatch.setenv("ADMIN_PASSWORD", "environment-password")
    assert Settings(_env_file=env_file).admin_password == "environment-password"
