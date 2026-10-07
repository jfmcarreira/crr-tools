"""Run legacy assertions unchanged, replacing only their backend/service transports."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "migration/contracts"
TEST_FILES = ["src/server/app.integration.test.ts", "src/server/services/calendar.test.ts",
              "src/server/services/classification.test.ts", "src/server/services/bracket.test.ts",
              "src/shared/finalSeeding.test.ts"]


def main(freeze: bool = False):
    if freeze:
        for name in TEST_FILES:
            destination = CONTRACTS / name
            if destination.exists():
                raise FileExistsError(f"Refusing to overwrite {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "apps/tournament" / name, destination)
        print("Preserved legacy assertions under migration/contracts without modifying source snapshots.")
        return
    modules = ROOT / "apps/tournament/node_modules"
    if not modules.is_dir():
        raise RuntimeError("Run make tournament-install first.")
    work = ROOT / ".migration/port-compat"
    work.mkdir(parents=True, exist_ok=True)
    staging = work / "tests"
    staging.mkdir(parents=True, exist_ok=True)
    if not (staging / "node_modules").exists():
        (staging / "node_modules").symlink_to(modules, target_is_directory=True)
    (staging / "package.json").write_text('{"private":true,"type":"module"}\n')
    (staging / "vitest.config.mjs").write_text("export default {test:{include:['src/**/python.*.test.ts']}};\n")
    for name in TEST_FILES:
        destination = staging / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CONTRACTS / name, destination)
    STAGING = staging
    server = STAGING / "src/server"
    shutil.copyfile(ROOT / "migration/python_fastify_adapter.mjs", server / "python_fastify_adapter.mjs")
    shutil.copyfile(ROOT / "migration/python_domain_adapter.mjs", server / "python_domain_adapter.mjs")
    files = []
    for source, module, replacement in [
        (server / "app.integration.test.ts", "./app.js", "./python_fastify_adapter.mjs"),
        (server / "services/calendar.test.ts", "./calendar.js", "../python_domain_adapter.mjs"),
        (server / "services/classification.test.ts", "./classification.js", "../python_domain_adapter.mjs"),
        (server / "services/bracket.test.ts", "./bracket.js", "../python_domain_adapter.mjs"),
        (STAGING / "src/shared/finalSeeding.test.ts", "./finalSeeding", "../server/python_domain_adapter.mjs"),
    ]:
        text = source.read_text()
        original = f"from '{module}'"
        assert text.count(original) == 1, source
        destination = source.with_name("python." + source.name)
        text = text.replace(original, f"from '{replacement}'")
        if "from './auth.js'" in text:
            text = text.replace("from './auth.js'", "from './python_fastify_adapter.mjs'")
        destination.write_text(text)
        files.append(str(destination.relative_to(STAGING)))
    env = os.environ | {
        "TOURNAMENT_BACKEND": str(ROOT / "apps/tournament/backend"),
        "TOURNAMENT_PYTHON": str(ROOT / ".venv/bin/python"),
        "TOURNAMENT_WORK": str(work),
        "TOURNAMENT_BRIDGE": str(ROOT / "migration/python_domain_bridge.py"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(["node", str(STAGING / "node_modules/vitest/vitest.mjs"), "run", *files,
                             "--reporter=default", "--reporter=json", f"--outputFile={work / 'tests.json'}"],
                            cwd=STAGING, env=env)
    if result.returncode == 0:
        raw = json.loads((work / "tests.json").read_text())
        report = {
            "passed": raw["numPassedTests"],
            "tests": [{"name": test["fullName"], "status": test["status"]}
                      for suite in raw["testResults"] for test in suite["assertionResults"]],
            "contract_sha256": {name: hashlib.sha256((CONTRACTS / name).read_bytes()).hexdigest()
                                for name in TEST_FILES},
        }
        output = ROOT / "migration/phase3"
        output.mkdir(parents=True, exist_ok=True)
        (output / "compatibility.json").write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="One-time preservation of the unchanged legacy assertions")
    main(parser.parse_args().freeze)
