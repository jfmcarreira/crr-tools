"""Host-independent affected-app selection for GitHub and Gitea Actions."""

import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"pyproject.toml", "uv.lock", ".python-version", "Makefile", ".dockerignore", "compose.yaml", "pyrightconfig.json"}


def affected(paths: list[str]) -> dict[str, bool]:
    result = {"tournament": False, "shifts": False}
    for path in paths:
        if path in ROOT_FILES or path.startswith((".github/workflows/", ".gitea/workflows/", "packages/", "tools/ci_changes.py", "tools/release.py", "tools/test_automation.py")):
            result = {key: True for key in result}
        elif path.startswith("apps/tournament/") or path.startswith("migration/fixtures/tournament"):
            result["tournament"] = True
        elif path.startswith("apps/shifts/") or path in {"migration/check_shifts_structure.py", "migration/phase4/baseline.json", "migration/phase5/shifts-definition-overrides.json", "migration/fixtures/shifts.sqlite"}:
            result["shifts"] = True
    return result


def changes(base: str, head: str) -> dict[str, bool]:
    if not base or set(base) == {"0"}:
        return {"tournament": True, "shifts": True}
    result = subprocess.run(["git", "diff", "--name-only", base, head, "--"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return affected(result.stdout.splitlines())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = changes(args.base, args.head)
    text = "".join(f"{key}={str(value).lower()}\n" for key, value in result.items())
    if args.output:
        with args.output.open("a") as output:
            output.write(text)
    print(text, end="")
