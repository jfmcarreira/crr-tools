"""Smoke-test independently built images using ephemeral synthetic databases."""

import json
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen
from urllib.parse import urlsplit
from uuid import uuid4


class PageResources(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"img", "script"} and attributes.get("src"):
            self.urls.append(attributes["src"] or "")
        elif tag == "link" and attributes.get("rel") in {"stylesheet", "icon"}:
            self.urls.append(attributes.get("href") or "")


def check(image: str, port: int, environment: dict[str, str], routes: list[str], proxy_prefix: str = "",
          legacy_fixture: Path | None = None, expected_state: dict | None = None) -> None:
    name = f"crr-migration-{uuid4().hex[:12]}"
    command = ["docker", "run", "--rm", "--detach", "--name", name,
               "--tmpfs", "/data:mode=1777", "--publish", f"127.0.0.1::{port}"]
    for key, value in environment.items():
        command.extend(["--env", f"{key}={value}"])
    if legacy_fixture is not None:
        command.extend(["--mount", f"type=bind,source={legacy_fixture},target=/legacy.sqlite,readonly"])
    command.append(image)
    if legacy_fixture is not None:
        command.extend(["sh", "-c", "cp /legacy.sqlite /data/tournament.sqlite && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080 --no-proxy-headers"])
    subprocess.run(command, check=True, capture_output=True, text=True)
    try:
        binding = subprocess.check_output(["docker", "port", name, str(port)], text=True).strip()
        base = f"http://{binding}"
        for _ in range(100):
            try:
                with urlopen(base + routes[0], timeout=1) as response:
                    assert response.status == 200
                break
            except OSError:
                time.sleep(0.1)
        else:
            logs = subprocess.check_output(["docker", "logs", name], text=True, stderr=subprocess.STDOUT)
            raise RuntimeError(f"{image} did not become ready:\n{logs}")
        for route in routes:
            with urlopen(base + route, timeout=5) as response:
                assert response.status == 200, route
                body = response.read()
                if route == "/api/public/state":
                    if expected_state is not None:
                        assert json.loads(body) == expected_state
                    else:
                        assert json.loads(body)["tournament"]["name"] == "Torneio"
                elif route in {"/results", "/login"}:
                    assert b"<html" in body.lower(), route
                    resources = PageResources()
                    resources.feed(body.decode())
                    assert resources.urls, route
                    for url in resources.urls:
                        path = urlsplit(url).path
                        # Tournament's legacy sub-path deployment strips the prefix at its proxy.
                        if proxy_prefix and path.startswith(proxy_prefix + "/"):
                            path = path[len(proxy_prefix):]
                        with urlopen(base + path, timeout=5) as resource:
                            assert resource.status == 200, url
                            if path.endswith(".png"):
                                assert resource.read().startswith(b"\x89PNG\r\n\x1a\n"), url
        print(f"{image}: container startup and {', '.join(routes)} passed")
    finally:
        subprocess.run(["docker", "rm", "--force", name], check=True, capture_output=True)


if __name__ == "__main__":
    check("crr-tournament", 8080, {
        "ADMIN_PASSWORD": "migration-smoke-only-password",
        "SESSION_SECRET": "migration-smoke-only-secret",
    }, ["/api/public/state", "/results"], proxy_prefix="/jogo")
    fixtures = Path(__file__).resolve().parents[1] / "migration/fixtures"
    check("crr-tournament", 8080, {
        "ADMIN_PASSWORD": "migration-smoke-only-password",
        "SESSION_SECRET": "migration-smoke-only-secret",
    }, ["/api/public/state", "/results"], proxy_prefix="/jogo",
          legacy_fixture=fixtures / "tournament.sqlite",
          expected_state=json.loads((fixtures / "tournament-state.json").read_text()))
    check("crr-shifts", 8000, {
        "DATABASE_URL": "sqlite:////data/smoke.db",
        "SECRET_KEY": "migration-smoke-only-secret",
        "INITIAL_ADMIN_PASSWORD": "migration-smoke-only-password",
        "SMTP_HOST": "",
    }, ["/health", "/login"])
