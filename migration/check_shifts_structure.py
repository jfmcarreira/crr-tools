"""Compare schema, ORM relationships, routes, existing data and Shifts workflows."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "migration/phase4"
FIXTURE = ROOT / "migration/fixtures/shifts.sqlite"


def definitions(backend: Path) -> dict[str, str]:
    result = {}
    for path in (backend / "app").rglob("*.py"):
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in result:
                    raise RuntimeError(f"Ambiguous top-level definition: {node.name}")
                result[node.name] = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
    return result


def rows(path: Path, normalize: bool = False) -> dict:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        result = {table: [dict(row) for row in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid')] for table in tables}
    if normalize:
        for values in result.values():
            for row in values:
                for key in ["created_at", "updated_at", "sent_at"]:
                    if row.get(key) is not None:
                        row[key] = "<timestamp>"
                if "password_hash" in row:
                    row["password_hash"] = "<password-hash>"
    return result


def orm_signature(Base):
    from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint, UniqueConstraint, inspect
    def default(value):
        if value is None:
            return None
        argument = value.arg
        if callable(argument):
            return {"callable": getattr(argument, "__qualname__", argument.__name__)}
        return str(argument)
    tables = {}
    for name, table in sorted(Base.metadata.tables.items()):
        constraints = []
        for constraint in table.constraints:
            data = {"type": type(constraint).__name__, "name": constraint.name}
            if isinstance(constraint, (PrimaryKeyConstraint, UniqueConstraint, ForeignKeyConstraint)):
                data["columns"] = [column.name for column in constraint.columns]
            if isinstance(constraint, CheckConstraint):
                data["sql"] = str(constraint.sqltext)
            if isinstance(constraint, ForeignKeyConstraint):
                data.update(targets=[item.target_fullname for item in constraint.elements],
                            ondelete=constraint.ondelete, onupdate=constraint.onupdate)
            constraints.append(data)
        tables[name] = {
            "columns": [{"name": column.name, "type": str(column.type), "nullable": column.nullable,
                         "primary_key": column.primary_key, "default": default(column.default),
                         "server_default": default(column.server_default), "onupdate": default(column.onupdate)}
                        for column in table.columns],
            "constraints": sorted(constraints, key=lambda value: json.dumps(value, sort_keys=True)),
            "indexes": sorted([{"name": index.name, "unique": index.unique, "columns": [column.name for column in index.columns]}
                               for index in table.indexes], key=lambda value: value["name"]),
        }
    relationships = {}
    for mapper in Base.registry.mappers:
        relationships[mapper.class_.__name__] = {relation.key: {
            "target": relation.mapper.class_.__name__, "back_populates": relation.back_populates,
            "cascade": sorted(relation.cascade), "uselist": relation.uselist,
            "pairs": sorted((str(local), str(remote)) for local, remote in relation.local_remote_pairs),
            "order_by": [str(item) for item in relation.order_by] if relation.order_by is not False else [],
        } for relation in inspect(mapper.class_).relationships}
    return {"tables": tables, "relationships": relationships}


def differences(expected, actual, path=""):
    if expected == actual:
        return []
    if isinstance(expected, dict) and isinstance(actual, dict):
        result = []
        for key in sorted(expected.keys() | actual.keys()):
            result.extend(differences(expected.get(key), actual.get(key), path + "/" + str(key)))
        return result
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        return [item for index, (before, after) in enumerate(zip(expected, actual)) for item in differences(before, after, path + f"/{index}")]
    if isinstance(expected, str) and isinstance(actual, str):
        first = next((index for index, (before, after) in enumerate(zip(expected, actual)) if before != after), 0)
        return [{"path": path, "expected": expected[max(0, first - 60):first + 120], "actual": actual[max(0, first - 60):first + 120]}]
    return [{"path": path, "expected": expected, "actual": actual}]


def normalized_report(value):
    result = json.loads(json.dumps(value))
    for scenario in result["workflows"].values():
        for request in scenario["requests"]:
            if request["path"] == "/admin/notifications":
                # Delivery times vary between runs; retain all other log-page markup.
                request["body"] = re.sub(r"<td>\d{2}/\d{2}/\d{4} \d{2}:\d{2}</td>",
                                          "<td><notification-time></td>", request["body"])
    return result


def workflow(app, sessions, models, database: Path, prefix: str):
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from pypdf import PdfReader
    from io import BytesIO
    records = []
    clients = []
    def client():
        value = TestClient(app, root_path=prefix)
        clients.append(value)
        return value
    def call(c, method, path, data=None, expected=None):
        response = c.request(method, prefix + path, data=data, follow_redirects=False)
        if expected is not None:
            assert response.status_code == expected, (method, path, response.status_code, response.text)
        body = response.text if "application/pdf" not in response.headers.get("content-type", "") else "\n".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
        body = re.sub(r'(name="csrf_token" value=")[^"]+', r'\1<csrf>', body)
        body = re.sub(r"DTSTAMP:[^\r\n]+", "DTSTAMP:<timestamp>", body)
        records.append({"method": method, "path": path, "status": response.status_code,
                        "headers": {key: response.headers[key] for key in ["content-type", "location", "content-disposition", "cache-control"] if key in response.headers},
                        "body": body})
        return response
    def csrf(c):
        page = c.get(prefix + "/login", follow_redirects=False)
        if page.status_code != 200:
            page = c.get(prefix + "/account")
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        assert token
        return token.group(1)
    def sign_in(username):
        c = client()
        token = csrf(c)
        call(c, "POST", "/login", {"username": username, "password": "secret123", "csrf_token": token}, 303)
        return c, token
    def submit(c, token, path, data=None, status=303):
        return call(c, "POST", path, {**(data or {}), "csrf_token": token}, status)
    anonymous = client()
    call(anonymous, "GET", "/health", expected=200)
    call(anonymous, "GET", "/login", expected=200)
    for path in ["/account", "/admin/teams", "/admin/users", "/admin/schedules", "/swaps"]:
        call(anonymous, "GET", path, expected=401)
    call(anonymous, "POST", "/login", {"username": "member-a", "password": "secret123", "csrf_token": "wrong"}, 400)
    a, a_token = sign_in(" MEMBER-A ")
    b, b_token = sign_in("member-b")
    admin, admin_token = sign_in("phase4-admin")
    for path in ["/account", "/calendar", "/swaps", "/swaps/new?year=2030&month=1", "/?year=2030&month=1", "/export/schedule"]:
        call(a, "GET", path, expected=200)
    call(a, "GET", "/admin/users", expected=403)
    call(anonymous, "GET", "/calendar/phase4-feed-a.ics", expected=200)
    call(anonymous, "GET", "/calendar/not-a-token.ics", expected=404)
    with sessions() as db:
        schedule = db.scalar(select(models.Schedule).where(models.Schedule.slug == "phase4-rotation"))
        schedule_id = schedule.id
        assignments = list(db.scalars(select(models.Assignment).where(models.Assignment.schedule_id == schedule_id).order_by(models.Assignment.date)))
        ids = [row.id for row in assignments]
        north = db.scalar(select(models.Team).where(models.Team.name == "Equipa Norte")).id
        south = db.scalar(select(models.Team).where(models.Team.name == "Equipa Sul")).id
    call(a, "GET", f"/export/schedule.pdf?schedule_id={schedule_id}&start_date=2030-01-01&end_date=2030-01-31", expected=200)
    submit(a, a_token, f"/assignments/{ids[0]}/swap", {"target_assignment_id": ids[1], "message": "Teste de troca"})
    with sessions() as db:
        swap_id = db.scalar(select(models.SwapRequest.id))
        assert db.get(models.SwapRequest, swap_id).status == "open"
    submit(b, b_token, f"/swaps/{swap_id}/accept")
    with sessions() as db:
        assert db.get(models.SwapRequest, swap_id).status == "pending_approval"
        assert db.get(models.Assignment, ids[0]).team_id == north
    submit(admin, admin_token, f"/swaps/{swap_id}/approve")
    with sessions() as db:
        assert db.get(models.Assignment, ids[0]).team_id == south
        assert db.get(models.Assignment, ids[1]).team_id == north
        assert db.get(models.Assignment, ids[0]).source == "swap"
    submit(admin, admin_token, f"/swaps/{swap_id}/revert")
    with sessions() as db:
        assert db.get(models.Assignment, ids[0]).team_id == north
        assert db.get(models.Assignment, ids[1]).team_id == south
        assert db.get(models.SwapRequest, swap_id).status == "reverted"
    for path in ["/admin/teams", "/admin/users", "/admin/schedules", f"/admin/schedules/{schedule_id}?year=2030&month=1", "/admin/assign?on=2030-01-05", "/admin/notifications", "/admin/month"]:
        call(admin, "GET", path)
    submit(admin, admin_token, f"/admin/schedules/{schedule_id}/apply-rotation", {"year": 2030, "month": 1})
    with sessions() as db:
        assert db.get(models.Assignment, ids[0]).source == "manual"
        assert db.get(models.Assignment, ids[1]).source == "manual"
        assert db.get(models.Assignment, ids[2]).source == "swap"
    submit(admin, admin_token, f"/admin/schedules/{schedule_id}/clear-from", {"year": 2030, "month": 1})
    with sessions() as db:
        assert db.get(models.Assignment, ids[2]).team_id == north
        assert db.get(models.Assignment, ids[3]).team_id is None
        assert db.get(models.Assignment, ids[3]).source == "generated"
    submit(admin, admin_token, "/admin/assign", {"assignment_id": ids[3], "team_id": south})
    submit(admin, admin_token, "/admin/teams", {"name": "Equipa temporária", "email": "TEMP@example.com", "notify_email": "on"})
    with sessions() as db:
        temporary_team = db.scalar(select(models.Team).where(models.Team.name == "Equipa temporária")).id
    submit(admin, admin_token, f"/admin/teams/{temporary_team}/update", {"name": "Equipa editada", "is_active": "on"})
    call(admin, "GET", f"/admin/teams/{temporary_team}/delete", expected=200)
    submit(admin, admin_token, f"/admin/teams/{temporary_team}/delete")
    submit(admin, admin_token, "/admin/users", {"name": "Utilizador temporário", "username": "temporary", "password": "secret123"})
    with sessions() as db:
        temporary_user = db.scalar(select(models.User).where(models.User.username == "temporary")).id
    submit(admin, admin_token, f"/admin/users/{temporary_user}/update", {"name": "Editado", "username": "edited", "is_active": "on"})
    submit(admin, admin_token, f"/admin/users/{temporary_user}/delete")
    submit(a, a_token, "/account", {"new_password": "secret123"})
    call(a, "GET", "/account", expected=200)
    submit(a, a_token, "/account", {"new_password": "new-secret123"})
    call(a, "GET", "/account", expected=200)
    submit(a, a_token, "/logout")
    call(a, "GET", "/account", expected=401)
    for c in clients:
        c.close()
    return {"requests": records, "rows": rows(database, normalize=True)}


def main(backend: Path, capture: bool):
    backend = backend.resolve()
    sys.path.insert(0, str(backend))
    REPORT.mkdir(parents=True, exist_ok=True)
    (ROOT / ".migration").mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="shifts-phase4-", dir=ROOT / ".migration") as temporary:
        database = Path(temporary) / "shifts.sqlite"
        os.environ.update({"DATABASE_URL": f"sqlite:///{database}", "BACKUP_DIR": str(Path(temporary) / "backups"),
                           "SECRET_KEY": "phase4-test-only-secret", "ROOT_PATH": "", "BASE_URL": "http://testserver",
                           "INITIAL_ADMIN_USERNAME": "phase4-admin", "INITIAL_ADMIN_PASSWORD": "secret123",
                           "INITIAL_ADMIN_NAME": "Administrador de teste", "INITIAL_ADMIN_EMAIL": "admin@example.com",
                           "SMTP_HOST": "", "CALENDAR_TOKEN": "phase4-whole-rota", "SESSION_HTTPS_ONLY": "false"})
        from datetime import date, time
        from fastapi.testclient import TestClient
        from sqlalchemy import select
        from app.main import app
        from app import models
        from app.database import Base, SessionLocal, engine, run_migrations
        from app.config import settings
        from app.security import hash_password
        class CaptureDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 10, 7)
        if capture and not FIXTURE.exists():
            run_migrations()
            # App startup initializes the same initial administrator and schedules as production.
            with TestClient(app):
                pass
            with SessionLocal() as db:
                users = [models.User(name=f"Membro {letter}", username=f"member-{letter}", password_hash=hash_password("secret123"), is_active=True) for letter in ["a", "b"]]
                db.add_all(users)
                db.flush()
                teams = [models.Team(name=name, user=user, email=f"{letter}@example.com", calendar_token=f"phase4-feed-{letter}") for name, user, letter in [("Equipa Norte", users[0], "a"), ("Equipa Sul", users[1], "b"), ("Equipa partilhada", users[0], "c")]]
                db.add_all(teams)
                schedule = models.Schedule(name="Rotação Phase 4", slug="phase4-rotation", schedule_type="rotation", weekdays="5", rotation_anchor_date=date(2030, 1, 5), start_time=time(12), end_time=time(14), requires_manager_approval=True)
                db.add(schedule)
                db.flush()
                db.add_all([models.RotationMember(schedule=schedule, team=team, position=index) for index, team in enumerate(teams[:2], 1)])
                for day, team, source in [(5, teams[0], "generated"), (12, teams[1], "manual"), (19, teams[0], "swap"), (26, teams[1], "generated")]:
                    db.add(models.Assignment(schedule=schedule, date=date(2030, 1, day), team=team, source=source))
                db.commit()
            with sqlite3.connect(database) as source, sqlite3.connect(FIXTURE) as destination:
                source.backup(destination)
        result = {"definitions": definitions(backend), "orm": orm_signature(Base), "openapi": app.openapi(),
                  "migrations": {str(path.relative_to(backend / "migrations")): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((backend / "migrations").rglob("*")) if path.is_file() and "__pycache__" not in path.parts},
                  "workflows": {}}
        # Resolve FastAPI's deferred annotations before freezing application clocks.
        # Only runtime date operations change; request schemas retain datetime.date.
        for name, module in list(sys.modules.items()):
            if name.startswith("app.") and getattr(module, "date", None) is date:
                setattr(module, "date", CaptureDate)
        fixture_rows = rows(FIXTURE)
        for prefix in ["", "/crr"]:
            engine.dispose()
            shutil.copyfile(FIXTURE, database)
            settings.root_path = prefix
            app.root_path = prefix
            with TestClient(app) as startup:
                assert rows(database) == fixture_rows, "Startup altered the existing fixture"
            result["workflows"][prefix] = workflow(app, SessionLocal, models, database, prefix)
        engine.dispose()
        results = ROOT / ".migration/phase4-results"
        results.mkdir(parents=True, exist_ok=True)
        output = REPORT / "baseline.json" if capture else results / "refactored.json"
        if capture and output.exists():
            raise FileExistsError(f"Refusing to overwrite {output}")
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
        if not capture:
            baseline = json.loads((REPORT / "baseline.json").read_text())
            override_path = ROOT / "migration/phase5/shifts-definition-overrides.json"
            overrides = {}
            if override_path.exists():
                override_report = json.loads(override_path.read_text())
                assert override_report["baseline_sha256"] == hashlib.sha256((REPORT / "baseline.json").read_bytes()).hexdigest()
                overrides = override_report["definitions"]
                for name, fingerprints in overrides.items():
                    assert baseline["definitions"][name] == fingerprints["before"], name
                    assert result["definitions"][name] == fingerprints["after"], name
                    baseline["definitions"][name] = fingerprints["after"]
            comparison = differences(normalized_report(baseline), normalized_report(result))
            (results / "differences.json").write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n")
            assert not comparison, f"{len(comparison)} structural/workflow differences; inspect .migration/phase4-results/differences.json"
            verification = {"definitions_preserved": len(result["definitions"]) - len(overrides),
                            "orm_mapping_and_relationships_unchanged": True,
                            "openapi_unchanged": True, "migration_files_unchanged": True,
                            "existing_fixture_rows_preserved_at_startup": True,
                            "workflow_requests_matched": sum(len(value["requests"]) for value in result["workflows"].values()),
                            "deployment_prefixes": list(result["workflows"]),
                            "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                            "baseline_sha256": hashlib.sha256((REPORT / "baseline.json").read_bytes()).hexdigest()}
            verification_path = REPORT / "verification.json"
            if overrides:
                verification["shared_infrastructure_delegations"] = overrides
                verification_path = ROOT / "migration/phase5/shifts-compatibility.json"
            verification_path.write_text(json.dumps(verification, indent=2) + "\n")
        print(f"Shifts {'baseline captured' if capture else 'structural/workflow parity verified'}: {sum(len(value['requests']) for value in result['workflows'].values())} requests across both deployment prefixes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, default=ROOT / "apps/shifts/backend")
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    main(args.backend, args.capture)
