import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
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


class ReleaseAssetClient:
    def __init__(self, releases, payloads):
        self.releases = releases
        self.payloads = payloads

    def repository(self, full_name):
        owner, repo = full_name.split("/", 1)
        return {
            "full_name": full_name,
            "name": repo,
            "description": "Repository fallback description",
            "owner": {"login": owner},
        }

    def stable_releases(self, full_name):
        return self.releases

    def fetch_bytes_url(self, url):
        return self.payloads[url]


def plugin_zip(manifest, prefix="", missing=(), extras=None):
    files = manifest.get(
        "files",
        ["manifest.json", "device.json", "plugin.js", "README.md"],
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative_path in files:
            if relative_path in missing:
                continue
            archive_path = f"{prefix}{relative_path}"
            if relative_path == "manifest.json":
                payload = json.dumps(manifest).encode("utf-8")
            elif relative_path.endswith(".json"):
                payload = b"{}\n"
            elif relative_path.endswith(".js"):
                payload = b"module.exports = {};\n"
            else:
                payload = f"fixture for {relative_path}\n".encode("utf-8")
            archive.writestr(archive_path, payload)
        for path, payload in (extras or {}).items():
            archive.writestr(path, payload)
    return buffer.getvalue()


class CatalogBuilderTests(unittest.TestCase):
    def test_normalize_version_requires_three_parts_and_supports_v_prefix(self):
        self.assertEqual(build_catalog.normalize_version("v0.1.2"), "0.1.2")
        self.assertEqual(build_catalog.normalize_version("1.2.3"), "1.2.3")
        self.assertIsNone(build_catalog.normalize_version("1.2"))
        self.assertIsNone(build_catalog.normalize_version("1.2.3.4"))
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
                "version": "0.1.2",
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
            "tag_name": "v0.1.2",
            "html_url": "https://github.com/jadehawk/send2ereader.xp-plugin/releases/tag/v0.1.2",
            "published_at": "2026-10-01T12:00:00Z",
        }

        entry = build_catalog.build_entry(client, repo, release)

        self.assertIsNotNone(entry)
        self.assertEqual(entry["version"], "0.1.2")
        self.assertEqual(
            entry["base"],
            "https://raw.githubusercontent.com/jadehawk/send2ereader.xp-plugin/v0.1.2/",
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

    def test_pin_raw_github_base_uses_commit_sha_for_branch(self):
        class PinClient:
            def __init__(self):
                self.calls = []

            def commit_sha(self, full_name, ref):
                self.calls.append((full_name, ref))
                return "a" * 40

        client = PinClient()

        self.assertEqual(
            build_catalog.pin_raw_github_base(
                client,
                "https://raw.githubusercontent.com/itsthisjustin/sd-plugins/main/bookfusion/",
            ),
            f"https://raw.githubusercontent.com/itsthisjustin/sd-plugins/{'a' * 40}/bookfusion/",
        )
        self.assertEqual(
            build_catalog.pin_raw_github_base(
                client,
                "https://raw.githubusercontent.com/marczykm/month-wallpaper-crosspoint-plugin/refs/heads/main/",
            ),
            f"https://raw.githubusercontent.com/marczykm/month-wallpaper-crosspoint-plugin/{'a' * 40}/",
        )
        self.assertEqual(
            client.calls,
            [
                ("itsthisjustin/sd-plugins", "main"),
                ("marczykm/month-wallpaper-crosspoint-plugin", "main"),
            ],
        )

    def test_curated_catalog_imports_only_whitelisted_plugins(self):
        class CuratedClient:
            def fetch_json_url(self, url):
                return {
                    "plugins": [
                        {
                            "name": "bookfusion",
                            "title": "BookFusion",
                            "description": "Browse books.",
                            "author": "Diirge",
                            "version": "1.2.0",
                            "base": "https://raw.githubusercontent.com/itsthisjustin/sd-plugins/main/bookfusion/",
                            "files": [
                                "manifest.json",
                                "device.json",
                                "plugin.js",
                                "README.md",
                            ],
                        },
                        {
                            "name": "send2ereader",
                            "title": "Old Send2Ereader",
                            "description": "Legacy entry.",
                            "author": "Jadehawk",
                            "version": "0.1.0",
                            "base": "https://example.invalid/",
                            "files": ["manifest.json", "device.json"],
                        },
                    ]
                }

            def commit_sha(self, full_name, ref):
                return "b" * 40

        whitelist = {
            "repositories": [],
            "catalogs": [
                {
                    "url": "https://example.test/catalog.json",
                    "plugins": ["bookfusion"],
                }
            ],
        }

        plugins = build_catalog.curated_catalog_plugins(CuratedClient(), whitelist)

        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0]["name"], "bookfusion")
        self.assertEqual(plugins[0]["version"], "1.2.0")
        self.assertEqual(
            plugins[0]["base"],
            f"https://raw.githubusercontent.com/itsthisjustin/sd-plugins/{'b' * 40}/bookfusion/",
        )
        self.assertEqual(plugins[0]["source_catalog"], "https://example.test/catalog.json")

    def test_release_plugin_wins_over_curated_duplicate(self):
        curated = [
            {
                "name": "send2ereader",
                "title": "Send2Ereader",
                "version": "0.1.0",
            }
        ]
        release = [
            {
                "name": "send2ereader",
                "title": "Send2Ereader",
                "version": "0.1.2.2",
            }
        ]

        merged = build_catalog.merge_plugins(release, curated)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["version"], "0.1.2.2")

    def test_release_asset_plugin_wins_over_other_duplicate_sources(self):
        curated = [{"name": "readest", "title": "Readest", "version": "0.1.0"}]
        release = [{"name": "readest", "title": "Readest", "version": "0.2.0"}]
        asset = [{"name": "readest", "title": "Readest", "version": "0.3.0"}]

        merged = build_catalog.merge_plugins(release, curated, asset)

        self.assertEqual(merged[0]["version"], "0.3.0")

    def test_load_whitelist_accepts_manual_release_asset_repository_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "whitelist.json"
            path.write_text(
                json.dumps(
                    {
                        "repositories": [],
                        "release_asset_repositories": ["readest/readest"],
                        "catalogs": [],
                    }
                ),
                encoding="utf-8",
            )

            whitelist = build_catalog.load_whitelist(path)

        self.assertEqual(
            whitelist["release_asset_repositories"],
            ["readest/readest"],
        )

    def test_release_asset_repository_uses_latest_stable_release_with_matching_zip(self):
        manifest = {
            "title": "Readest",
            "description": "Readest for CrossPoint.",
            "author": "Readest",
            "version": "0.12.10",
            "files": ["manifest.json", "device.json", "plugin.js", "README.md"],
        }
        payload = plugin_zip(manifest, prefix="readest/")
        releases = [
            {
                "tag_name": "v0.13.0",
                "assets": [{"name": "Readest-0.13.0-windows.zip"}],
            },
            {
                "tag_name": "v0.12.10",
                "html_url": "https://github.com/readest/readest/releases/tag/v0.12.10",
                "published_at": "2026-09-21T00:00:00Z",
                "assets": [
                    {
                        "name": "Readest-0.12.10.crosspoint-plugin.zip",
                        "browser_download_url": "memory://readest",
                    }
                ],
            },
        ]
        client = ReleaseAssetClient(releases, {"memory://readest": payload})

        with tempfile.TemporaryDirectory() as temp_dir:
            mirror_root = Path(temp_dir) / "release-assets"
            plugins = build_catalog.release_asset_plugins(
                client,
                ["readest/readest"],
                "jadehawk/PluginHub.crosspoint-plugin",
                mirror_root,
            )
            mirrored_manifest = mirror_root / "readest" / "0.12.10" / "manifest.json"
            self.assertTrue(mirrored_manifest.exists())
            self.assertEqual(json.loads(mirrored_manifest.read_text())["version"], "0.12.10")

        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0]["name"], "readest")
        self.assertEqual(plugins[0]["version"], "0.12.10")
        self.assertEqual(plugins[0]["release"], "v0.12.10")
        self.assertEqual(
            plugins[0]["release_asset"],
            "Readest-0.12.10.crosspoint-plugin.zip",
        )
        self.assertEqual(
            plugins[0]["base"],
            "https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/release-assets/readest/0.12.10/",
        )

    def test_release_asset_repository_processes_multiple_matching_zips(self):
        first_manifest = {
            "name": "first-plugin",
            "version": "1.0.0",
            "files": ["manifest.json", "device.json"],
        }
        second_manifest = {
            "name": "second-plugin",
            "version": "2.0.0",
            "files": ["manifest.json", "plugin.js"],
        }
        releases = [
            {
                "tag_name": "v9.9.9",
                "assets": [
                    {
                        "name": "First.crosspoint-plugin.zip",
                        "browser_download_url": "memory://first",
                    },
                    {
                        "name": "Second.crosspoint-plugin.zip",
                        "browser_download_url": "memory://second",
                    },
                ],
            }
        ]
        client = ReleaseAssetClient(
            releases,
            {
                "memory://first": plugin_zip(first_manifest),
                "memory://second": plugin_zip(second_manifest),
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            plugins = build_catalog.release_asset_plugins(
                client,
                ["owner/monorepo"],
                "jadehawk/PluginHub.crosspoint-plugin",
                Path(temp_dir) / "release-assets",
            )

        self.assertEqual([plugin["name"] for plugin in plugins], ["first-plugin", "second-plugin"])
        self.assertEqual([plugin["version"] for plugin in plugins], ["1.0.0", "2.0.0"])
        self.assertTrue(all(plugin["release"] == "v9.9.9" for plugin in plugins))

    def test_release_asset_rejects_unsafe_archive_paths(self):
        manifest = {
            "name": "unsafe",
            "version": "1.0.0",
            "files": ["manifest.json", "device.json"],
        }
        payload = plugin_zip(manifest, extras={"../secret.txt": b"nope"})

        with self.assertRaises(build_catalog.CatalogError):
            build_catalog.inspect_release_asset(payload, "owner/repo", "unsafe.crosspoint-plugin.zip")

    def test_release_asset_rejects_missing_declared_files(self):
        manifest = {
            "name": "broken",
            "version": "1.0.0",
            "files": ["manifest.json", "device.json", "assets/icon.bin"],
        }
        payload = plugin_zip(manifest, missing={"assets/icon.bin"})

        with self.assertRaises(build_catalog.CatalogError):
            build_catalog.inspect_release_asset(payload, "owner/repo", "broken.crosspoint-plugin.zip")

    def test_mirror_rejects_same_version_payload_mutation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "release-assets"
            build_catalog.mirror_plugin_payload(
                root,
                "example",
                "1.0.0",
                {"manifest.json": b"one", "device.json": b"{}"},
            )
            with self.assertRaises(build_catalog.CatalogError):
                build_catalog.mirror_plugin_payload(
                    root,
                    "example",
                    "1.0.0",
                    {"manifest.json": b"two", "device.json": b"{}"},
                )

    def test_configured_release_asset_repository_without_matching_zip_fails(self):
        client = ReleaseAssetClient(
            [{"tag_name": "v1.0.0", "assets": [{"name": "desktop.zip"}]}],
            {},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(build_catalog.CatalogError):
                build_catalog.release_asset_plugins(
                    client,
                    ["owner/monorepo"],
                    "jadehawk/PluginHub.crosspoint-plugin",
                    Path(temp_dir) / "release-assets",
                )

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
                        "name": "Plugin Hub",
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
