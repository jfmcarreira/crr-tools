import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ci_changes import affected
from release import release_plan


class ChangedPaths(unittest.TestCase):
    def test_each_app_is_selected_independently(self):
        self.assertEqual(affected(["apps/tournament/frontend/src/App.vue"]), {"tournament": True, "shifts": False})
        self.assertEqual(affected(["apps/shifts/backend/app/routers/auth.py"]), {"tournament": False, "shifts": True})

    def test_common_changes_select_both(self):
        for path in ["packages/crr-brand/styles/tokens.css", "packages/crr-python/src/crr_common/database.py", "uv.lock", "Makefile", ".github/workflows/ci.yaml"]:
            self.assertEqual(affected([path]), {"tournament": True, "shifts": True})

    def test_documentation_does_not_build_apps(self):
        self.assertEqual(affected(["README.md", "docs/RELEASES.md"]), {"tournament": False, "shifts": False})

    def test_ttlock_selects_only_its_consumer(self):
        self.assertEqual(affected(["packages/ttlock/src/ttlock/client.py"]), {"tournament": False, "shifts": True})
        self.assertEqual(affected(["packages/ttlock/tests/test_client.py", "apps/tournament/Dockerfile"]), {"tournament": True, "shifts": True})


class ReleaseTags(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for app, version in [("tournament", "1.0.0"), ("shifts", "0.1.0")]:
            folder = self.root / f"apps/{app}/backend"
            folder.mkdir(parents=True)
            (folder / "pyproject.toml").write_text(f'[project]\nversion="{version}"\n')
        folder = self.root / "apps/tournament/frontend"
        folder.mkdir()
        (folder / "package.json").write_text(json.dumps({"version": "1.0.0"}))

    def test_tag_selects_one_image_and_registry(self):
        selected = release_plan("shifts-v0.1.0", self.root, owner="Owner")
        self.assertEqual(selected["image"], "ghcr.io/owner/crr-shifts")
        self.assertEqual(selected["dockerfile"], "apps/shifts/Dockerfile")
        self.assertEqual(selected["publish_latest"], "true")
        self.assertEqual(release_plan("tournament-v1.0.0", self.root, owner="Owner")["registry"], "ghcr.io")

    def test_explicit_registry_override(self):
        selected = release_plan("shifts-v0.1.0", self.root, owner="Owner", registry="registry.example.test:5000")
        self.assertEqual(selected["image"], "registry.example.test:5000/owner/crr-shifts")

    def test_shifts_release_does_not_read_tournament_metadata(self):
        (self.root / "apps/tournament/frontend/package.json").unlink()
        self.assertEqual(release_plan("shifts-v0.1.0", self.root)["app"], "shifts")

    def test_invalid_or_mismatched_tags_fail(self):
        for tag in ["v1.0.0", "tournament-v9.0.0", "shifts-v1", "shifts-v0.1.0;cmd"]:
            with self.assertRaises(ValueError):
                release_plan(tag, self.root)

    def test_tournament_versions_must_agree(self):
        (self.root / "apps/tournament/frontend/package.json").write_text('{"version":"2.0.0"}')
        with self.assertRaises(ValueError):
            release_plan("tournament-v1.0.0", self.root)

    def test_prereleases_do_not_promote_latest(self):
        (self.root / "apps/shifts/backend/pyproject.toml").write_text('[project]\nversion="0.2.0-rc.1"\n')
        self.assertEqual(release_plan("shifts-v0.2.0-rc.1", self.root)["publish_latest"], "false")


if __name__ == "__main__":
    unittest.main()
