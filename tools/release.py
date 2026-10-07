"""Validate independent app tags and produce a single-image release plan."""

import argparse
import json
from pathlib import Path
import re
import tomllib
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TAG = re.compile(r"^(tournament|shifts)-v(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$")


def release_plan(tag: str, root: Path = ROOT, server: str = "", owner: str = "", registry: str = "") -> dict[str, str]:
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError("Use an independent tournament-vX.Y.Z or shifts-vX.Y.Z tag")
    app, version = match.groups()
    metadata = tomllib.loads((root / f"apps/{app}/backend/pyproject.toml").read_text())
    if metadata["project"]["version"] != version:
        raise ValueError(f"{tag} does not match the {app} backend version")
    if app == "tournament":
        frontend = json.loads((root / "apps/tournament/frontend/package.json").read_text())
        if frontend["version"] != version:
            raise ValueError("Tournament frontend/backend versions must agree")
    host = urlsplit(server).netloc
    registry = registry or ("ghcr.io" if host == "github.com" else host)
    if registry and not re.fullmatch(r"[A-Za-z0-9.-]+(?::\d+)?", registry):
        raise ValueError("Registry must be a hostname with an optional port")
    if owner and not re.fullmatch(r"[A-Za-z0-9_.-]+", owner):
        raise ValueError("Invalid registry owner")
    image = f"{registry}/{owner.lower()}/crr-{app}" if registry and owner else f"crr-{app}"
    return {"app": app, "version": version, "dockerfile": f"apps/{app}/Dockerfile",
            "registry": registry, "image": image, "publish_latest": str("-" not in version).lower()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--server", default="")
    parser.add_argument("--owner", default="")
    parser.add_argument("--registry", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = release_plan(args.tag, server=args.server, owner=args.owner, registry=args.registry)
    if args.output:
        with args.output.open("a") as output:
            output.write("".join(f"{key}={value}\n" for key, value in result.items()))
    print(json.dumps(result, indent=2))
