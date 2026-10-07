"""Preserve portable baseline evidence and verify captured SQLite contents."""

import json
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET

from migration_baseline import ROOT, SOURCES, hashes


def main() -> None:
    output = ROOT / "migration/baseline"
    output.mkdir(parents=True, exist_ok=True)
    for app, source in SOURCES.items():
        results = ROOT / "migration/results" / app
        manifest = json.loads((results / "baseline.json").read_text())
        assert hashes(source) == manifest["sha256"], f"Snapshot changed: {app}"
        assert all(check["exit_code"] == 0 for check in manifest["checks"])
        for check in manifest["checks"]:
            check["command"] = [arg.replace(str(ROOT) + "/", "") for arg in check["command"]]
        if app == "tournament":
            report = json.loads((results / "tests.json").read_text())
            manifest["tests"] = [
                {"name": test["fullName"], "status": test["status"]}
                for suite in report["testResults"] for test in suite["assertionResults"]
            ]
        else:
            report = ET.parse(results / "tests.xml")
            manifest["tests"] = [
                {"name": f"{test.attrib['classname']}.{test.attrib['name']}", "status": "passed"}
                for test in report.findall(".//testcase")
                if not any(child.tag in {"failure", "error", "skipped"} for child in test)
            ]
        (output / f"{app}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    fixtures = ROOT / "migration/fixtures"
    with sqlite3.connect(f"file:{fixtures / 'tournament.sqlite'}?mode=ro&immutable=1", uri=True) as db:
        db.row_factory = sqlite3.Row
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        expected = json.loads((fixtures / "tournament-rows.json").read_text())
        assert len(expected) == 9
        for table, rows in expected.items():
            assert table.isidentifier()
            actual = [dict(row) for row in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
            assert actual == rows, table
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='alembic_version'").fetchall()
    artifacts = {"fixtures": hashes(fixtures), "screenshots": hashes(ROOT / "migration/screenshots")}
    (output / "artifacts.json").write_text(json.dumps(artifacts, indent=2) + "\n")
    print("Preserved both green baseline reports; original sources and all nine SQLite tables verified.")


if __name__ == "__main__":
    main()
