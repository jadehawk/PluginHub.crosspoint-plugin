import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_catalog.py"
SPEC = importlib.util.spec_from_file_location("build_catalog", MODULE_PATH)
build_catalog = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_catalog)


class FakeClient:
    def __init__(self, manifest=None, root=None):
        self.manifest = manifest or {}
        self.root = root or []

    def root_contents(self, full_name, ref):
        return self.root

    def json_file(self, full_name, ref, path):
        return self.manifest


class CatalogBuilderTests(unittest.TestCase):
    def test_normalize_version_supports_four_parts_and_v_prefix(self):
        self.assertEqual(build_catalog.normalize_version("v0.1.1.2"), "0.1.1.2")
        self.assertEqual(build_catalog.normalize_version("1.2"), "1.2")
        self.assertEqual(build_catalog.normalize_version("1.2.3"), "1.2.3")
        self.assertIsNone(build_catalog.normalize_version("1"))
        self.assertIsNone(build_catalog.normalize_version("1.2.3.4.5"))
        self.assertIsNone(build_catalog.normalize_version("v1.2.3-beta"))

    def test_plugin_id_prefers_valid_manifest_name(self):
        manifest = {"name": "send2ereader"}
        self.assertEqual(
            build_catalog.derive_plugin_id("SomethingElse.xp-plugin", manifest),
            "send2ereader",
        )

    def test_plugin_id_falls_back_to_repo_name(self):
        self.assertEqual(
            build_catalog.derive_plugin_id("PluginHub.crosspoint-plugin", {}),
            "pluginhub",
        )
        self.assertEqual(
            build_catalog.derive_plugin_id("Month-Wallpaper.crosspoint-plugin", {}),
            "month-wallpaper",
        )
        self.assertEqual(
            build_catalog.derive_plugin_id("month-wallpaper-crosspoint-plugin", {}),
            "month-wallpaper",
        )

    def test_runtime_files_default_to_conventional_plugin_files(self):
        root = {"manifest.json", "device.json", "plugin.js", "README.md", "tests"}
        self.assertEqual(
            build_catalog.safe_runtime_files({}, root),
            ["manifest.json", "device.json", "plugin.js", "README.md"],
        )

    def test_runtime_files_allow_explicit_nested_assets(self):
        manifest = {
            "files": [
                "manifest.json",
                "device.json",
                "assets/icon.bin",
                "README.md",
            ]
        }
        self.assertEqual(
            build_catalog.safe_runtime_files(manifest, {"manifest.json", "device.json"}),
            manifest["files"],
        )

    def test_runtime_files_reject_traversal_and_non_plugins(self):
        self.assertIsNone(
            build_catalog.safe_runtime_files(
                {"files": ["manifest.json", "device.json", "../secret"]},
                {"manifest.json", "device.json"},
            )
        )
        self.assertIsNone(
            build_catalog.safe_runtime_files(
                {"files": ["manifest.json", "README.md"]},
                {"manifest.json", "README.md"},
            )
        )

    def test_build_entry_uses_release_tag_as_immutable_base(self):
        client = FakeClient(
            manifest={
                "name": "send2ereader",
                "title": "Send2Ereader",
                "description": "Send books to CrossPoint.",
                "author": "Jadehawk",
                "version": "0.1.1.2",
                "files": ["manifest.json", "device.json", "plugin.js", "README.md"],
            },
            root=[
                {"name": "manifest.json", "type": "file"},
                {"name": "device.json", "type": "file"},
                {"name": "plugin.js", "type": "file"},
                {"name": "README.md", "type": "file"},
            ],
        )
        repo = {
            "full_name": "jadehawk/send2ereader.xp-plugin",
            "name": "send2ereader.xp-plugin",
            "description": "fallback",
            "owner": {"login": "jadehawk"},
        }
        release = {
            "tag_name": "v0.1.1.2",
            "html_url": "https://github.com/jadehawk/send2ereader.xp-plugin/releases/tag/v0.1.1.2",
            "published_at": "2026-10-01T12:00:00Z",
        }

        entry = build_catalog.build_entry(client, repo, release)

        self.assertIsNotNone(entry)
        self.assertEqual(entry["version"], "0.1.1.2")
        self.assertEqual(
            entry["base"],
            "https://raw.githubusercontent.com/jadehawk/send2ereader.xp-plugin/v0.1.1.2/",
        )
        self.assertEqual(entry["files"], client.manifest["files"])

    def test_build_entry_rejects_manifest_release_version_mismatch(self):
        client = FakeClient(
            manifest={
                "name": "example",
                "version": "0.1.1",
                "files": ["manifest.json", "device.json"],
            },
            root=[
                {"name": "manifest.json", "type": "file"},
                {"name": "device.json", "type": "file"},
            ],
        )
        repo = {
            "full_name": "owner/example.xp-plugin",
            "name": "example.xp-plugin",
            "owner": {"login": "owner"},
        }
        release = {"tag_name": "v0.1.2"}

        self.assertIsNone(build_catalog.build_entry(client, repo, release))

    def test_discovery_does_not_globally_search_xp_plugin_names(self):
        self.assertIn("topic:crosspoint-plugin", build_catalog.SEARCH_QUERIES)
        self.assertIn('in:name "crosspoint-plugin"', build_catalog.SEARCH_QUERIES)
        self.assertNotIn('in:name ".xp-plugin"', build_catalog.SEARCH_QUERIES)

    def test_rate_limit_aborts_catalog_build_instead_of_publishing_partial_results(self):
        class RateLimitedClient:
            def search_repositories(self, query):
                return [
                    {
                        "full_name": "owner/example.xp-plugin",
                        "name": "example.xp-plugin",
                        "owner": {"login": "owner"},
                    }
                ]

            def latest_stable_release(self, full_name):
                raise build_catalog.GitHubRateLimitError("rate limited")

        with self.assertRaises(build_catalog.GitHubRateLimitError):
            build_catalog.discover_plugins(RateLimitedClient())

    def test_write_catalog_does_not_churn_timestamp_when_plugins_are_unchanged(self):
        plugins = [{"name": "example", "title": "Example"}]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "generated_at": "2026-10-01T00:00:00Z",
                        "plugins": plugins,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            changed = build_catalog.write_catalog(path, plugins)
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertFalse(changed)
            self.assertEqual(payload["generated_at"], "2026-10-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
