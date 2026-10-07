"""Recover absent source snapshots exclusively from checksum-verified staging files."""

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    copies = []
    reports = {}
    for app in ("tournament", "shifts"):
        manifest = json.loads((ROOT / f"migration/baseline/{app}.json").read_text())
        destination = ROOT / manifest["source"]
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite snapshot: {destination}")
        for relative, checksum in manifest["sha256"].items():
            source = ROOT / ".migration" / app / relative
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != checksum:
                raise RuntimeError(f"No verified recovery source: {source}")
            target = destination / relative
            if not target.is_relative_to(destination):
                raise ValueError(relative)
            copies.append((source, target))
        reports[app] = {"source": manifest["source"], "files_verified": len(manifest["sha256"]),
                        "nested_git_history_recovered": False}
    for source, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    output = ROOT / "migration/phase6"
    output.mkdir(parents=True, exist_ok=True)
    (output / "snapshot-recovery.json").write_text(json.dumps(reports, indent=2) + "\n")
    print(f"Recovered {len(copies)} legacy source files matching their original checksums; existing files were not overwritten.")


if __name__ == "__main__":
    main()
