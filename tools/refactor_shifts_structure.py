"""One-time structural generator: relocate definitions verbatim and wire explicit imports.

It only creates new production modules. Existing callers and retired files are
updated separately, so no source snapshot or application work is overwritten.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps/shifts/backend/app"
REPORT = ROOT / "migration/phase4"

HELPERS = {
    "dependencies": "_redirect _current_user _require_user _require_admin _user_teams _user_team_ids _user_label _csrf _check_csrf _flash _context _parse_month _month_nav _safe_back",
    "schedule_helpers": "_next_dates _schedule_card _schedule_groups _active_schedules _all_schedules _get_schedule _schedule_team_ids _schedule_teams _schedule_teams_map _render_admin_schedules _shared_calendar_url _pattern_map",
    "swap_helpers": "_active_request _swap_side _swap_partner _reject_swap _rejectable _swap_ownership_holds _complete_swap _accepting_team",
    "assignment_helpers": "_apply_pattern_to_open_rows _apply_pattern_forward _clear_assignments_from _save_assignments _default_team _set_assignee _notify_assignment_changes _month_assignments _apply_rotation_to_rows _generate_rotation_range",
    "admin.user_helpers": "_admin_teams _usable_admin_users",
    "admin.teams": "_users_by_id _chosen_user _loses_last_team _team_removal_impact _team_removal_blocker _require_removable",
    "admin.users": "_user_removal_blocker _new_user _assign_user_to_teams",
    "admin.schedules": "_parse_time _open_swap_requests",
    "admin.assignments": "_schedule_page _assign_day_url",
    "calendar": "_calendar_token",
    "swaps": "_create_swap",
}
MODEL_MODULES = {"User": "user", "Team": "team", "Schedule": "schedule",
                 "MonthlyPattern": "schedule", "RotationMember": "schedule",
                 "Assignment": "assignment", "SwapRequest": "swap", "NotificationLog": "notification"}
SERVICE_PATHS = {"app.calendar": "app.services.calendar_feed", "app.pdf": "app.services.pdf",
                 "app.notifications": "app.services.notifications", "app.scheduling": "app.services.scheduling",
                 "app.bootstrap": "app.services.bootstrap"}


def segment(text: str, node: ast.AST) -> str:
    start = min([node.lineno, *(item.lineno for item in getattr(node, "decorator_list", []))])
    return "\n".join(text.splitlines()[start - 1:node.end_lineno])


def loaded(nodes) -> set[str]:
    return {item.id for node in nodes for item in ast.walk(node) if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)}


def relative_import(caller: str, target: str, names: list[str]) -> str:
    package, target_parts = caller.split(".")[:-1], target.split(".")
    common = 0
    while common < min(len(package), len(target_parts)) and package[common] == target_parts[common]:
        common += 1
    module = "." * (len(package) - common + 1) + ".".join(target_parts[common:])
    return f"from {module} import {', '.join(sorted(names))}"


def imports_for(tree: ast.Module, names: set[str], caller: str) -> list[str]:
    imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            aliases = [item for item in node.names if (item.asname or item.name.split('.')[0]) in names]
            if aliases:
                imports.append(ast.unparse(ast.Import(names=aliases)))
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            aliases = [item for item in node.names if (item.asname or item.name) in names]
            if aliases:
                if node.level:
                    target = "app." + node.module
                    target = SERVICE_PATHS.get(target, target)
                    imports.append(relative_import(caller, target, [item.name for item in aliases]))
                else:
                    imports.append(ast.unparse(ast.ImportFrom(module=node.module, names=aliases, level=0)))
    return imports


def route_owner(path: str) -> str:
    if path in {"/login", "/logout"}:
        return "auth"
    if path == "/account":
        return "account"
    if path.startswith("/calendar"):
        return "calendar"
    if path.startswith("/export/"):
        return "exports"
    if path in {"/", "/health"}:
        return "dashboard"
    if path.startswith("/swaps") or path.startswith("/assignments/"):
        return "swaps"
    if path.startswith("/admin/teams"):
        return "admin.teams"
    if path.startswith("/admin/users"):
        return "admin.users"
    if path == "/admin/notifications":
        return "admin.notifications"
    if path == "/admin/assign" or any(value in path for value in ("/assignments", "/swaps/", "/apply-pattern", "/clear-from", "/apply-rotation")):
        return "admin.assignments"
    if path.startswith(("/admin/schedules", "/admin/rotation")) or path == "/admin/month":
        return "admin.schedules"
    raise ValueError(f"Unmapped route: {path}")


def web_modules() -> tuple[dict[Path, str], dict]:
    text = (APP / "web.py").read_text()
    tree = ast.parse(text)
    definitions = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    ownership = {name: f"app.routers.{module}" for module, names in HELPERS.items() for name in names.split()}
    routes = []
    for name, node in definitions.items():
        decorators = [item for item in node.decorator_list if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and isinstance(item.func.value, ast.Name) and item.func.value.id == "router"]
        if decorators:
            owners = {route_owner(item.args[0].value) for item in decorators}
            assert len(owners) == 1, name
            ownership[name] = "app.routers." + owners.pop()
            routes.extend({"method": item.func.attr.upper(), "path": item.args[0].value, "function": name} for item in decorators)
    assert definitions.keys() == ownership.keys(), (definitions.keys() - ownership.keys(), ownership.keys() - definitions.keys())
    outputs, graph = {}, {}
    for module in sorted(set(ownership.values())):
        nodes = [node for name, node in definitions.items() if ownership[name] == module]
        names = loaded(nodes)
        imports = imports_for(tree, names | ({"APIRouter"} if "router" in names else set()), module)
        dependencies = {}
        for name in names & definitions.keys():
            owner = ownership[name]
            if owner != module:
                dependencies.setdefault(owner, []).append(name)
        graph[module] = set(dependencies)
        imports.extend(relative_import(module, owner, names) for owner, names in sorted(dependencies.items()))
        content = "from __future__ import annotations\n\n" + "\n".join(imports) + "\n\n"
        if "router" in names:
            content += "router = APIRouter()\n\n"
        if "ALL_WEEKDAYS" in names:
            content += "ALL_WEEKDAYS = frozenset(range(7))\n\n"
        content += "\n\n\n".join(segment(text, node) for node in nodes) + "\n"
        outputs[APP / (module.removeprefix("app.").replace(".", "/") + ".py")] = content
    def visit(module, stack):
        assert module not in stack, f"Circular route-helper dependency: {stack + [module]}"
        for dependency in graph[module]:
            visit(dependency, stack + [module])
    for module in graph:
        visit(module, [])
    ordered = ["auth", "account", "calendar", "exports", "dashboard", "swaps", "admin.teams", "admin.users", "admin.schedules", "admin.assignments", "admin.notifications"]
    outputs[APP / "routers/__init__.py"] = "from fastapi import APIRouter\n\n" + "\n".join(f"from .{name} import router as {name.replace('.', '_')}_router" for name in ordered) + "\n\nrouter = APIRouter()\nfor domain_router in (\n" + "".join(f"    {name.replace('.', '_')}_router,\n" for name in ordered) + "):\n    router.include_router(domain_router)\n"
    outputs[APP / "routers/admin/__init__.py"] = ""
    fingerprints = {name: hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest() for name, node in definitions.items()}
    return outputs, {"routes": routes, "function_sha256": fingerprints, "ownership": ownership}


def model_modules() -> dict[Path, str]:
    text = (APP / "models.py").read_text()
    tree = ast.parse(text)
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    assert classes.keys() == MODEL_MODULES.keys()
    outputs = {}
    for name in sorted(set(MODEL_MODULES.values())):
        module = "app.models." + name
        nodes = [node for key, node in classes.items() if MODEL_MODULES[key] == name]
        names = loaded(nodes)
        imports = imports_for(tree, names, module)
        references = {key: value for key, value in MODEL_MODULES.items() if key in names and value != name}
        if references:
            imports.append("from typing import TYPE_CHECKING")
        content = "from __future__ import annotations\n\n" + "\n".join(imports) + "\n\n"
        if references:
            content += "if TYPE_CHECKING:\n" + "\n".join(f"    from .{target} import {key}" for key, target in sorted(references.items())) + "\n\n"
        content += "\n\n\n".join(segment(text, node) for node in nodes) + "\n"
        outputs[APP / f"models/{name}.py"] = content
    outputs[APP / "models/__init__.py"] = "from ..database import Base\n" + "\n".join(relative_import("app.models.__init__", f"app.models.{name}", [key for key, owner in MODEL_MODULES.items() if owner == name]) for name in ["user", "team", "schedule", "assignment", "swap", "notification"]) + "\n\n__all__ = " + repr(["Base", *MODEL_MODULES]) + "\n"
    return outputs


def security_modules() -> dict[Path, str]:
    text = (APP / "security.py").read_text()
    tree = ast.parse(text)
    nodes = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    outputs = {}
    for name in ["passwords", "csrf"]:
        selected = [node for node in nodes if (isinstance(node, ast.FunctionDef) and node.name == "new_csrf_token") == (name == "csrf")]
        imports = imports_for(tree, loaded(selected), f"app.security.{name}")
        outputs[APP / f"security/{name}.py"] = "from __future__ import annotations\n\n" + "\n".join(imports) + "\n\n" + "\n\n\n".join(segment(text, node) for node in selected) + "\n"
    outputs[APP / "security/__init__.py"] = "from .csrf import new_csrf_token\nfrom .passwords import ITERATIONS, MIN_PASSWORD_LENGTH, hash_password, verify_password\n\n__all__ = ['ITERATIONS', 'MIN_PASSWORD_LENGTH', 'hash_password', 'verify_password', 'new_csrf_token']\n"
    return outputs


def main():
    outputs, manifest = web_modules()
    outputs.update(model_modules())
    outputs.update(security_modules())
    for path in outputs:
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")
    for path, text in outputs.items():
        ast.parse(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "structure.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Generated {len(outputs)} modules; {len(manifest['routes'])} routes and all function bodies preserved verbatim.")


if __name__ == "__main__":
    main()
