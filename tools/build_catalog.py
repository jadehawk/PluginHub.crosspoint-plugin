#!/usr/bin/env python3
"""Build Plugin Hub's CrossPoint catalog from GitHub repositories and releases."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "https://api.github.com"
SEARCH_QUERIES = (
    "topic:crosspoint-plugin",
    'in:name "crosspoint-plugin"',
)
CONVENTIONAL_FILES = ("manifest.json", "device.json", "plugin.js", "README.md")
VERSION_RE = re.compile(r"^[vV]?(\d+(?:\.\d+){1,3})$")
PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class CatalogError(RuntimeError):
    pass


class GitHubRateLimitError(CatalogError):
    pass


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def _request_json(self, path: str, params: dict[str, str | int] | None = None) -> Any:
        url = f"{API_BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "PluginHub.crosspoint-plugin catalog builder",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            error_type = GitHubRateLimitError if exc.code in (403, 429) else CatalogError
            raise error_type(f"GitHub API {exc.code} for {url}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise CatalogError(f"GitHub request failed for {url}: {exc}") from exc

    def search_repositories(self, query: str, max_pages: int = 10) -> list[dict[str, Any]]:
        repositories: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            payload = self._request_json(
                "/search/repositories",
                {"q": query, "sort": "stars", "order": "desc", "per_page": 100, "page": page},
            )
            items = payload.get("items", [])
            if not isinstance(items, list):
                raise CatalogError(f"GitHub search returned an invalid items list for {query!r}")
            repositories.extend(item for item in items if isinstance(item, dict))
            if len(items) < 100:
                break
        return repositories

    def latest_stable_release(self, full_name: str) -> dict[str, Any] | None:
        releases = self._request_json(f"/repos/{full_name}/releases", {"per_page": 20})
        if not isinstance(releases, list):
            raise CatalogError(f"GitHub releases response is invalid for {full_name}")
        for release in releases:
            if isinstance(release, dict) and not release.get("draft") and not release.get("prerelease"):
                return release
        return None

    def root_contents(self, full_name: str, ref: str) -> list[dict[str, Any]]:
        payload = self._request_json(f"/repos/{full_name}/contents", {"ref": ref})
        if not isinstance(payload, list):
            raise CatalogError(f"Repository root is not a directory for {full_name}@{ref}")
        return [item for item in payload if isinstance(item, dict)]

    def json_file(self, full_name: str, ref: str, path: str) -> dict[str, Any]:
        payload = self._request_json(
            f"/repos/{full_name}/contents/{urllib.parse.quote(path, safe='/')}",
            {"ref": ref},
        )
        if not isinstance(payload, dict) or payload.get("type") != "file":
            raise CatalogError(f"{path} is not a file in {full_name}@{ref}")
        if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
            raise CatalogError(f"{path} has an unsupported GitHub API encoding in {full_name}@{ref}")
        try:
            raw = base64.b64decode(payload["content"]).decode("utf-8")
            parsed = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise CatalogError(f"{path} is not valid UTF-8 JSON in {full_name}@{ref}") from exc
        if not isinstance(parsed, dict):
            raise CatalogError(f"{path} must contain a JSON object in {full_name}@{ref}")
        return parsed


def normalize_version(tag: str) -> str | None:
    match = VERSION_RE.fullmatch(tag.strip())
    return match.group(1) if match else None


def derive_plugin_id(repo_name: str, manifest: dict[str, Any]) -> str | None:
    declared = manifest.get("name")
    if isinstance(declared, str) and PLUGIN_ID_RE.fullmatch(declared):
        return declared

    name = repo_name
    for suffix in (".crosspoint-plugin", "-crosspoint-plugin", ".xp-plugin"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return name if PLUGIN_ID_RE.fullmatch(name) else None


def safe_runtime_files(manifest: dict[str, Any], root_names: set[str]) -> list[str] | None:
    declared = manifest.get("files")
    if declared is None:
        files = [name for name in CONVENTIONAL_FILES if name in root_names]
    elif isinstance(declared, list) and all(isinstance(item, str) for item in declared):
        files = list(dict.fromkeys(declared))
    else:
        return None

    if not files or len(files) > 64:
        return None
    for path in files:
        if (
            not path
            or path.startswith("/")
            or "\\" in path
            or ".." in path.split("/")
            or len(path) > 180
        ):
            return None
    if "manifest.json" not in files:
        return None
    if "device.json" not in files and "plugin.js" not in files:
        return None
    return files


def build_entry(
    client: GitHubClient,
    repo: dict[str, Any],
    release: dict[str, Any],
) -> dict[str, Any] | None:
    full_name = repo.get("full_name")
    repo_name = repo.get("name")
    tag = release.get("tag_name")
    if not all(isinstance(value, str) and value for value in (full_name, repo_name, tag)):
        return None

    version = normalize_version(tag)
    if version is None:
        print(f"skip {full_name}: release tag {tag!r} is not a 2-4 part numeric version", file=sys.stderr)
        return None

    root = client.root_contents(full_name, tag)
    root_names = {item.get("name") for item in root if item.get("type") == "file" and isinstance(item.get("name"), str)}
    if "manifest.json" not in root_names:
        print(f"skip {full_name}: release {tag} has no root manifest.json", file=sys.stderr)
        return None

    try:
        manifest = client.json_file(full_name, tag, "manifest.json")
    except CatalogError as exc:
        print(f"skip {full_name}: {exc}", file=sys.stderr)
        return None

    manifest_version = manifest.get("version")
    if not isinstance(manifest_version, str) or normalize_version(manifest_version) != version:
        print(
            f"skip {full_name}: manifest version {manifest_version!r} does not match release {tag!r}",
            file=sys.stderr,
        )
        return None

    plugin_id = derive_plugin_id(repo_name, manifest)
    if plugin_id is None:
        print(f"skip {full_name}: cannot derive a safe plugin id", file=sys.stderr)
        return None

    files = safe_runtime_files(manifest, root_names)
    if files is None:
        print(f"skip {full_name}: manifest files are missing or unsafe", file=sys.stderr)
        return None

    title = manifest.get("title") if isinstance(manifest.get("title"), str) else repo_name
    description = manifest.get("description") if isinstance(manifest.get("description"), str) else (repo.get("description") or "")
    author = manifest.get("author") if isinstance(manifest.get("author"), str) else repo.get("owner", {}).get("login", "")

    return {
        "name": plugin_id,
        "title": title,
        "description": description,
        "author": author,
        "version": version,
        "repository": full_name,
        "release": tag,
        "release_url": release.get("html_url", ""),
        "published_at": release.get("published_at", ""),
        "base": f"https://raw.githubusercontent.com/{full_name}/{urllib.parse.quote(tag, safe='')}/",
        "files": files,
    }


def discover_plugins(
    client: GitHubClient,
    excluded_repository: str | None = None,
    max_repositories: int | None = None,
) -> list[dict[str, Any]]:
    discovered: dict[str, dict[str, Any]] = {}
    for query in SEARCH_QUERIES:
        for repo in client.search_repositories(query):
            full_name = repo.get("full_name")
            if not isinstance(full_name, str):
                continue
            key = full_name.lower()
            if key not in discovered:
                discovered[key] = repo

    plugins: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for repo in discovered.values():
        full_name = repo.get("full_name", "")
        if excluded_repository and full_name.lower() == excluded_repository.lower():
            continue
        if repo.get("archived") or repo.get("disabled"):
            continue
        if max_repositories is not None and len(plugins) >= max_repositories:
            break

        try:
            release = client.latest_stable_release(full_name)
            if release is None:
                print(f"skip {full_name}: no stable GitHub release", file=sys.stderr)
                continue
            entry = build_entry(client, repo, release)
        except GitHubRateLimitError:
            raise
        except CatalogError as exc:
            print(f"skip {full_name}: {exc}", file=sys.stderr)
            continue
        if entry is None:
            continue
        if entry["name"] in seen_ids:
            print(f"skip {full_name}: duplicate plugin id {entry['name']!r}", file=sys.stderr)
            continue
        seen_ids.add(entry["name"])
        plugins.append(entry)

    plugins.sort(key=lambda item: (item["title"].casefold(), item["name"]))
    return plugins


def load_existing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_catalog(path: Path, plugins: list[dict[str, Any]]) -> bool:
    existing = load_existing(path)
    old_plugins = existing.get("plugins")
    generated_at = existing.get("generated_at")
    changed = old_plugins != plugins
    if changed or not isinstance(generated_at, str):
        generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "plugins": plugins,
    }
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    if previous == rendered:
        return False
    path.write_text(rendered, encoding="utf-8", newline="\n")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="catalog.json", help="catalog path to write")
    parser.add_argument(
        "--exclude-repository",
        default=os.environ.get("GITHUB_REPOSITORY", "jadehawk/PluginHub.crosspoint-plugin"),
        help="repository to exclude from its own catalog",
    )
    parser.add_argument("--max-repositories", type=int, default=None, help="optional accepted-plugin limit for testing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    client = GitHubClient(token)
    try:
        plugins = discover_plugins(client, args.exclude_repository, args.max_repositories)
    except CatalogError as exc:
        print(f"catalog build failed: {exc}", file=sys.stderr)
        return 1

    changed = write_catalog(Path(args.output), plugins)
    print(f"catalog {'updated' if changed else 'unchanged'}: {len(plugins)} plugins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
