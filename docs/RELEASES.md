# Independent releases

Each application owns its version, database, authentication and image. There is
no monorepo release number and no automatic deployment of the other app.

## Tags and metadata

- Tournament: `tournament-vX.Y.Z`, matching both
  `apps/tournament/backend/pyproject.toml` and
  `apps/tournament/frontend/package.json` (regenerate its lockfile when versioning).
- Shifts: `shifts-vX.Y.Z`, matching `apps/shifts/backend/pyproject.toml`.
- Prerelease tags such as `shifts-v0.2.0-rc.1` publish the versioned image without
  promoting `latest`. Stable tags publish the version and that app's `latest`.

Inspect the plan without creating or publishing a tag:

```sh
make release-plan TAG=tournament-v1.0.0
make release-plan TAG=shifts-v0.1.0
make tooling-test
```

After updating metadata and committing/reviewing the intended app changes, a
maintainer can create and push the independent tag. The workflow rejects invalid
tags/version mismatches, tests the selected app and common package, builds its
root-context Dockerfile, and publishes only `crr-tournament` or `crr-shifts`.

## Hosting and registry

The current remote is Gitea; use `.gitea/workflows/ci.yaml` and `release.yaml`.
Identical GitHub mirrors are under `.github/workflows/`. Gitea supports the
`github` context aliases used by these portable workflows.

The default registry is the Gitea server hostname. For GitHub it is `ghcr.io`.
Images are named `<registry>/<repository-owner>/crr-<app>:<version>`, with a
lowercase owner. Set the repository variable `CONTAINER_REGISTRY` to override
the registry hostname (optionally including a port).

Authentication uses `REGISTRY_USERNAME`/`REGISTRY_TOKEN` secrets when configured,
otherwise the actor/job token. Gitea deployments whose job token cannot publish
packages should configure a package-write token and matching registry username.
Tokens are passed to `docker/login-action`; they are not stored in source.

Enable repository Actions and provide an `ubuntu-latest` runner with Docker
build/push capability and access to the registry/action download hosts. The
workflows install Node 22 where needed and pinned uv, which provisions Python
3.13. Local builds/tests and release planning are verified; remote execution and
authenticated image publication have not been performed.

## Deploy a selected version

Use the independently published image/tag for the desired app and retain its
existing storage and environment contract. Tournament uses `/data/tournament.sqlite`
and UID/GID 1000. Shifts uses its separate `/data/bar_rota.db` volume. Preserve
`SESSION_SECRET` for Tournament session continuity and `SECRET_KEY` for Shifts.
The default Compose services can still be built and run independently locally.
