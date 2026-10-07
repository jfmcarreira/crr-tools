"""Run legacy checks in isolated copies without writing into source snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "tournament": ROOT / "originals/tournment-manager-web",
    "shifts": ROOT / "originals/crr-shifts",
}
IGNORED = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", "dist"}


def hashes(source: Path) -> dict[str, str]:
    if not source.is_dir():
        raise FileNotFoundError(f"Baseline source directory is missing: {source}")
    return {
        str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source.rglob("*"))
        if path.is_file() and not (set(path.relative_to(source).parts) & IGNORED)
    }


def run(app: str) -> bool:
    source = SOURCES[app]
    before = hashes(source)
    work = ROOT / ".migration" / app
    results = ROOT / "migration/results" / app
    results.mkdir(parents=True, exist_ok=True)
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(source, work, ignore=shutil.ignore_patterns(*IGNORED))
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    commands: list[list[str]]
    if app == "tournament":
        commands = [
            ["npm", "ci"],
            ["npm", "test", "--", "--reporter=default", "--reporter=json",
             f"--outputFile={results / 'tests.json'}"],
            ["npm", "run", "typecheck"],
            ["npm", "run", "build"],
        ]
    else:
        python = str(work / ".venv/bin/python")
        commands = [
            ["uv", "venv", "--python", "3.13", str(work / ".venv")],
            ["uv", "pip", "install", "--python", python, "-r", "requirements-dev.txt"],
            [python, "-m", "pytest", "-p", "no:cacheprovider",
             f"--junitxml={results / 'tests.xml'}"],
        ]
    checks = []
    try:
        for index, command in enumerate(commands):
            print(f"{app}: {' '.join(command)}", flush=True)
            result = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True)
            (results / f"{index + 1}.log").write_text(result.stdout + result.stderr)
            print(result.stdout + result.stderr, end="", flush=True)
            checks.append({"command": command, "exit_code": result.returncode})
            if result.returncode and index < (1 if app == "tournament" else 2):
                break
    finally:
        if hashes(source) != before:
            raise RuntimeError(f"Legacy snapshot changed: {source}")
        manifest = {"source": str(source.relative_to(ROOT)), "sha256": before,
                    "checks": checks}
        (results / "baseline.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return bool(checks) and len(checks) == len(commands) and all(
        check["exit_code"] == 0 for check in checks
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", choices=[*SOURCES, "all"], default="all", nargs="?")
    args = parser.parse_args()
    apps = SOURCES if args.app == "all" else [args.app]
    outcomes = [run(app) for app in apps]
    raise SystemExit(0 if all(outcomes) else 1)
