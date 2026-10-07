"""One-time Phase 1 source copy. Existing destinations are never overwritten."""

from pathlib import Path
import shutil

from migration_baseline import ROOT, SOURCES, hashes


def main() -> None:
    copies = []
    tournament = ROOT / "apps/tournament"
    shifts = ROOT / "apps/shifts"
    for name in ["src", "public", "index.html", "logo.png", "package.json", "package-lock.json",
                 "tsconfig.client.json", "tsconfig.server.json", "vite.config.ts", ".env.example"]:
        copies.append((SOURCES["tournament"] / name, tournament / name))
    for name in ["app", "migrations", "tests", "alembic.ini", "requirements.txt", "requirements-dev.txt"]:
        copies.append((SOURCES["shifts"] / name, shifts / "backend" / name))
    for name in ["docs", ".env.example"]:
        copies.append((SOURCES["shifts"] / name, shifts / name))
    for _, destination in copies:
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite {destination}")
    before = {app: hashes(source) for app, source in SOURCES.items()}
    for source, destination in copies:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
    assert before == {app: hashes(source) for app, source in SOURCES.items()}
    print("Copied both applications into apps/; legacy snapshots are unchanged.")


if __name__ == "__main__":
    main()
