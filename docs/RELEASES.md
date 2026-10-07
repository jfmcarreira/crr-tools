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

The primary repository is [jfmcarreira/crr-tools](https://github.com/jfmcarreira/crr-tools).
GitHub Actions CI and independent releases are defined in
`.github/workflows/ci.yaml` and `.github/workflows/release.yaml`.

The default registry is GitHub Container Registry (`ghcr.io`). Images are named
`ghcr.io/jfmcarreira/crr-tournament:<version>` and
`ghcr.io/jfmcarreira/crr-shifts:<version>`. Owners are normalized to lowercase.
Set the repository variable `CONTAINER_REGISTRY` to override the registry
hostname (optionally including a port).

GHCR authentication uses the GitHub actor and built-in `GITHUB_TOKEN`, with
`packages: write` permission granted to the release workflow. No extra registry
secret is required for the default configuration. Optional
`REGISTRY_USERNAME`/`REGISTRY_TOKEN` secrets supply credentials for an override
registry. Tokens are passed to `docker/login-action`; they are not stored in source.

Workflows use GitHub-hosted `ubuntu-latest` runners with Docker. They install
Node 22 where needed and pinned uv, which provisions Python 3.13. Enable Actions
in the repository and push the workflow changes; CI can also be run manually
from the Actions tab. Local checks and release planning are verified; execution
of these changes on GitHub and authenticated image publication remain unverified.

## Deploy a selected version

Use the independently published image/tag for the desired app and retain its
existing storage and environment contract. Tournament uses `/data/tournament.sqlite`
and UID/GID 1000. Shifts uses its separate `/data/bar_rota.db` volume. Preserve
`SESSION_SECRET` for Tournament session continuity and `SECRET_KEY` for Shifts.
The default Compose services can still be built and run independently locally.
