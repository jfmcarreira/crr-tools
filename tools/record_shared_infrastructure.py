"""Record the exact infrastructure delegation that supersedes one Phase 4 AST."""

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    baseline_path = ROOT / "migration/phase4/baseline.json"
    baseline = json.loads(baseline_path.read_text())
    database = ROOT / "apps/shifts/backend/app/database.py"
    function = next(node for node in ast.parse(database.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == "alembic_config")
    fingerprint = hashlib.sha256(ast.dump(function, include_attributes=False).encode()).hexdigest()
    report = {
        "baseline_sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
        "definitions": {"alembic_config": {
            "before": baseline["definitions"]["alembic_config"],
            "after": fingerprint,
            "shared_helper": "crr_common.migrations.migration_config",
        }},
    }
    path = ROOT / "migration/phase5/shifts-definition-overrides.json"
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print("Recorded the shared Alembic-config delegation; all other Phase 4 definitions stay guarded.")


if __name__ == "__main__":
    main()
