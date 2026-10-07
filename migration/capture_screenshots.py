"""Capture desktop/mobile legacy pages using synthetic data and isolated servers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.request import urlopen
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".migration"


def wait_for(url: str, process: subprocess.Popen) -> None:
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"Server exited before serving {url}")
        try:
            with urlopen(url, timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for {url}")


def main(migrated: bool = False, branding: bool = False, reference: Path | None = None) -> None:
    if branding:
        output = ROOT / "migration/phase2/screenshots" if migrated else WORK / "branding-baseline"
    else:
        output = WORK / "screenshots" if migrated else ROOT / "migration/screenshots"
    output.mkdir(parents=True, exist_ok=True)
    suffix = "-migrated" if migrated else ""
    tournament_source = ROOT / "apps/tournament/frontend" if migrated else WORK / "tournament"
    shifts_source = ROOT / "apps/shifts/backend" if migrated else WORK / "shifts"
    tournament_db = WORK / f"visual-tournament{suffix}.sqlite"
    shutil.copyfile(ROOT / "migration/fixtures/tournament.sqlite", tournament_db)
    env = os.environ | {
        "CAPTURE_DATABASE": str(tournament_db),
        "MIGRATION_SOURCE_DIR": str(tournament_source),
        "DATABASE_URL": f"sqlite:///{WORK / f'visual-shifts{suffix}.db'}",
        "BACKUP_DIR": str(WORK / "visual-backups"),
        "SECRET_KEY": "migration-visual-only-secret",
        "INITIAL_ADMIN_USERNAME": "migration-admin",
        "INITIAL_ADMIN_PASSWORD": "migration-fixture-password",
        "SMTP_HOST": "", "ROOT_PATH": "", "SESSION_HTTPS_ONLY": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
        "ADMIN_PASSWORD": "migration-fixture-password",
        "SESSION_SECRET": "migration-fixture-secret-not-for-production",
        "APP_BASE_PATH": "/", "DATABASE_PATH": str(tournament_db),
        "CLIENT_DIST_PATH": str(tournament_source / ("dist" if migrated else "dist/client")),
    }
    python = str(ROOT / ".venv/bin/python" if migrated else WORK / "shifts/.venv/bin/python")
    subprocess.run([python, "-m", "app.cli", "seed-demo"], cwd=shifts_source, env=env, check=True)
    processes = []
    logs = []
    try:
        for name, command, cwd in [
            ("tournament", [python, "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1",
                            "--port", "18080", "--no-proxy-headers"] if migrated else
             ["node", "--import", str(tournament_source / "node_modules/tsx/dist/loader.mjs"),
              "migration/capture_tournament.mjs", "--serve"], ROOT / "apps/tournament/backend" if migrated else ROOT),
            ("shifts", [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                        "--port", "18081"], shifts_source),
        ]:
            log = (WORK / f"visual-{name}.log").open("w")
            logs.append(log)
            processes.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log))
        wait_for("http://127.0.0.1:18080/api/public/state", processes[0])
        wait_for("http://127.0.0.1:18081/health", processes[1])
        captures = []
        layouts = {}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for size, width, height in [("desktop", 1440, 1000), ("mobile", 390, 844)]:
                    context = browser.new_context(viewport={"width": width, "height": height},
                                                  locale="pt-PT", timezone_id="Europe/Lisbon")
                    page = context.new_page()
                    page.clock.set_fixed_time(datetime(2026, 10, 7, 12, tzinfo=timezone.utc))

                    def capture(app: str, name: str, url: str, *, print_media: bool = False) -> None:
                        response = page.goto(url, wait_until="domcontentloaded")
                        assert response and response.status == 200, url
                        page.locator("h1").first.wait_for()
                        page.evaluate("document.fonts.ready")
                        page.wait_for_timeout(500)
                        page.emulate_media(media="print" if print_media else "screen")
                        filename = f"{app}-{name}-{size}.png"
                        if branding:
                            assert page.evaluate("Array.from(document.images).every(img => img.complete && img.naturalWidth > 0)"), filename
                            layouts[filename] = page.locator(
                                "h1, h2, h3, main, header, form, button, input, select, table, tr, th, td, img, "
                                ".panel, .auth-card, .day-card, .team-card, .match-result-card, "
                                ".match-result-card__score-fields span"
                            ).evaluate_all("""elements => elements.map(element => {
                                const rect = element.getBoundingClientRect();
                                return {tag: element.tagName, class: element.className,
                                    rect: ['x', 'y', 'width', 'height'].map(key => Math.round(rect[key] * 1000) / 1000)};
                            })""")
                            if migrated:
                                primary = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--crr-primary').trim()")
                                assert primary == "#ed1c24", filename
                        page.screenshot(path=str(output / filename), full_page=True, animations="disabled")
                        captures.append({"file": filename, "path": urlsplit(url).path,
                                         "viewport": {"width": width, "height": height},
                                         "media": "print" if print_media else "screen"})
                        page.emulate_media(media="screen")

                    tournament = "http://127.0.0.1:18080"
                    capture("tournament", "login", tournament + "/admin/login")
                    capture("tournament", "results", tournament + "/results")
                    login = context.request.post(tournament + "/api/auth/login",
                                                 data={"password": "migration-fixture-password"})
                    assert login.status == 200
                    capture("tournament", "teams", tournament + "/admin/teams")
                    capture("tournament", "match-cards-print", tournament + "/admin/match-cards", print_media=True)
                    # Separate contexts: cookies from the two apps share the same hostname.
                    context.close()
                    context = browser.new_context(viewport={"width": width, "height": height},
                                                  locale="pt-PT", timezone_id="Europe/Lisbon")
                    page = context.new_page()
                    page.clock.set_fixed_time(datetime(2026, 10, 7, 12, tzinfo=timezone.utc))
                    shifts = "http://127.0.0.1:18081"
                    capture("shifts", "login", shifts + "/login")
                    page.locator('[name="username"]').fill("migration-admin")
                    page.locator('[name="password"]').fill("migration-fixture-password")
                    page.locator('button[type="submit"]').click()
                    page.wait_for_url(shifts + "/")
                    capture("shifts", "dashboard", shifts + "/")
                    capture("shifts", "teams", shifts + "/admin/teams")
                    context.close()
            finally:
                browser.close()
        (output / "manifest.json").write_text(json.dumps(captures, indent=2) + "\n")
        if branding:
            (output / "layout.json").write_text(json.dumps(layouts, indent=2) + "\n")
            if migrated:
                baseline_layout = json.loads((WORK / "branding-baseline/layout.json").read_text())
                assert layouts.keys() == baseline_layout.keys()
                for filename, layout in layouts.items():
                    expected = baseline_layout[filename]
                    differences = [(index, before, after) for index, (before, after) in enumerate(zip(expected, layout))
                                   if before != after]
                    assert len(layout) == len(expected) and not differences, f"{filename}: {differences[:5]}"
                    if "match-cards-print" in filename:
                        assert (ROOT / "migration/screenshots" / filename).read_bytes() == (output / filename).read_bytes(), filename
                print(f"All {len(captures)} branded captures preserve legacy geometry; both print captures match byte-for-byte.")
                report = {
                    "captures": len(captures),
                    "legacy_geometry_preserved": True,
                    "print_captures_byte_identical": 2,
                    "primary_token": "#ed1c24",
                    "element_counts": {filename: len(layout) for filename, layout in layouts.items()},
                    "screenshot_sha256": {item["file"]: hashlib.sha256((output / item["file"]).read_bytes()).hexdigest()
                                          for item in captures},
                }
                (output.parent / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        elif migrated:
            baseline = ROOT / reference if reference else ROOT / "migration/screenshots"
            for item in captures:
                filename = item["file"]
                assert (baseline / filename).read_bytes() == (output / filename).read_bytes(), filename
            label = str(reference) if reference else "the legacy baseline"
            print(f"All {len(captures)} migrated screenshots match {label} byte-for-byte.")
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrated", action="store_true")
    parser.add_argument("--branding", action="store_true", help="Check layout geometry while permitting shared palette/asset changes")
    parser.add_argument("--reference", type=Path, help="Screenshot directory for exact migrated comparisons")
    args = parser.parse_args()
    main(args.migrated, args.branding, args.reference)
