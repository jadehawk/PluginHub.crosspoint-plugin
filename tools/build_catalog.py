#!/usr/bin/env python3
"""Build Plugin Hub's CrossPoint catalog from GitHub repositories and releases."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog_partitions import (
    COMMUNITY_CATALOG_MAX_BYTES,
    COMMUNITY_LIST_INDEX,
    compact_json,
    list_index_entries,
    partition_community_plugins,
    rendered_catalog_size,
    shard_filename,
)

API_BASE = "https://api.github.com"
SEARCH_QUERIES = (
    "topic:crosspoint-plugin",
    'in:name "crosspoint-plugin"',
)
CONVENTIONAL_FILES = ("manifest.json", "device.json", "plugin.js", "README.md")
VERSION_RE = re.compile(r"^[vV]?(\d+\.\d+\.\d+)$")
PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
RAW_GITHUB_BASE_RE = re.compile(
    r"^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/(.+)$"
)
RELEASE_ASSET_SUFFIX = ".crosspoint-plugin.zip"
RELEASE_ASSET_MIRROR_DIR = "release-assets"
MAX_RELEASE_ASSET_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 256
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_PLUGIN_FILE_BYTES = 8 * 1024 * 1024
MAX_PLUGIN_TOTAL_BYTES = 16 * 1024 * 1024


class CatalogError(RuntimeError):
    pass


class GitHubRateLimitError(CatalogError):
    pass


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token
        self._commit_sha_cache: dict[tuple[str, str], str] = {}

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

    def stable_releases(self, full_name: str, max_pages: int = 3) -> list[dict[str, Any]]:
        stable: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            releases = self._request_json(
                f"/repos/{full_name}/releases",
                {"per_page": 100, "page": page},
            )
            if not isinstance(releases, list):
                raise CatalogError(f"GitHub releases response is invalid for {full_name}")
            stable.extend(
                release
                for release in releases
                if isinstance(release, dict)
                and not release.get("draft")
                and not release.get("prerelease")
            )
            if len(releases) < 100:
                break
        return stable

    def latest_stable_release(self, full_name: str) -> dict[str, Any] | None:
        releases = self.stable_releases(full_name, max_pages=1)
        return releases[0] if releases else None

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

    def repository(self, full_name: str) -> dict[str, Any]:
        payload = self._request_json(f"/repos/{full_name}")
        if not isinstance(payload, dict):
            raise CatalogError(f"GitHub repository response is invalid for {full_name}")
        return payload

    def commit_sha(self, full_name: str, ref: str) -> str:
        cache_key = (full_name.lower(), ref)
        cached = self._commit_sha_cache.get(cache_key)
        if cached is not None:
            return cached

        payload = self._request_json(
            f"/repos/{full_name}/commits/{urllib.parse.quote(ref, safe='')}"
        )
        sha = payload.get("sha") if isinstance(payload, dict) else None
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
            raise CatalogError(f"GitHub commit response is invalid for {full_name}@{ref}")

        normalized = sha.lower()
        self._commit_sha_cache[cache_key] = normalized
        return normalized

    def fetch_json_url(self, url: str) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "PluginHub.crosspoint-plugin catalog builder",
        }
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise CatalogError(f"HTTP {exc.code} for {url}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise CatalogError(f"Request failed for {url}: {exc}") from exc
        except ValueError as exc:
            raise CatalogError(f"Response is not valid JSON: {url}") from exc
        if not isinstance(payload, dict):
            raise CatalogError(f"JSON root must be an object: {url}")
        return payload

    def fetch_bytes_url(self, url: str, max_bytes: int = MAX_RELEASE_ASSET_BYTES) -> bytes:
        headers = {
            "Accept": "application/octet-stream",
            "User-Agent": "PluginHub.crosspoint-plugin catalog builder",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        if int(content_length) > max_bytes:
                            raise CatalogError(f"release asset exceeds {max_bytes} bytes: {url}")
                    except ValueError:
                        pass
                payload = response.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            error_type = GitHubRateLimitError if exc.code in (403, 429) else CatalogError
            raise error_type(f"HTTP {exc.code} for {url}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise CatalogError(f"Request failed for {url}: {exc}") from exc
        if len(payload) > max_bytes:
            raise CatalogError(f"release asset exceeds {max_bytes} bytes: {url}")
        return payload


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


def load_whitelist(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"repositories": [], "release_asset_repositories": [], "catalogs": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogError(f"whitelist is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CatalogError("whitelist root must be an object")

    repositories = payload.get("repositories", [])
    release_asset_repositories = payload.get("release_asset_repositories", [])
    catalogs = payload.get("catalogs", [])
    if not isinstance(repositories, list) or not all(
        isinstance(item, str) and REPOSITORY_RE.fullmatch(item) for item in repositories
    ):
        raise CatalogError("whitelist repositories must be owner/repository strings")
    if not isinstance(release_asset_repositories, list) or not all(
        isinstance(item, str) and REPOSITORY_RE.fullmatch(item)
        for item in release_asset_repositories
    ):
        raise CatalogError(
            "whitelist release_asset_repositories must be owner/repository strings"
        )
    if not isinstance(catalogs, list) or not all(isinstance(item, dict) for item in catalogs):
        raise CatalogError("whitelist catalogs must be objects")

    return {
        "repositories": repositories,
        "release_asset_repositories": release_asset_repositories,
        "catalogs": catalogs,
    }


def load_blacklist(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {"repositories": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogError(f"blacklist is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CatalogError("blacklist root must be an object")

    repositories = payload.get("repositories", [])
    if not isinstance(repositories, list) or not all(
        isinstance(item, str) and REPOSITORY_RE.fullmatch(item) for item in repositories
    ):
        raise CatalogError("blacklist repositories must be owner/repository strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for repository in repositories:
        key = repository.lower()
        if key not in seen:
            normalized.append(repository)
            seen.add(key)
    return {"repositories": normalized}


def github_repository_from_url(url: str) -> str | None:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return None
    host = parsed.netloc.lower()
    parts = [part for part in parsed.path.split("/") if part]
    if host == "raw.githubusercontent.com" and len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    if host in {"github.com", "www.github.com"} and len(parts) >= 2:
        repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
        return f"{parts[0]}/{repo}"
    return None


def is_blacklisted_repository(repository: str | None, blacklisted: set[str]) -> bool:
    return isinstance(repository, str) and repository.lower() in blacklisted


def plugin_entry_is_blacklisted(plugin: dict[str, Any], blacklisted: set[str]) -> bool:
    repository = plugin.get("repository")
    if is_blacklisted_repository(repository if isinstance(repository, str) else None, blacklisted):
        return True
    for key in ("base", "source_catalog"):
        value = plugin.get(key)
        if isinstance(value, str) and is_blacklisted_repository(github_repository_from_url(value), blacklisted):
            return True
    return False


def filter_blacklisted_policy(policy: dict[str, Any], blacklisted: set[str]) -> dict[str, Any]:
    official = []
    for entry in policy.get("official", []):
        repository = entry.get("repository")
        source_catalog = entry.get("source_catalog")
        source_repository = github_repository_from_url(source_catalog) if isinstance(source_catalog, str) else None
        if is_blacklisted_repository(repository, blacklisted) or is_blacklisted_repository(source_repository, blacklisted):
            continue
        official.append(entry)
    return {"official": official}


def load_policy(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogError(f"catalog policy is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CatalogError("catalog policy root must be an object")

    official = payload.get("official", [])
    if not isinstance(official, list) or not all(isinstance(item, dict) for item in official):
        raise CatalogError("catalog policy official entries must be objects")

    seen_ids: set[str] = set()
    normalized: list[dict[str, str]] = []
    for entry in official:
        plugin_id = entry.get("plugin")
        repository = entry.get("repository")
        source_catalog = entry.get("source_catalog")
        if not isinstance(plugin_id, str) or PLUGIN_ID_RE.fullmatch(plugin_id) is None:
            raise CatalogError("catalog policy official plugin ids must be safe plugin ids")
        if plugin_id in seen_ids:
            raise CatalogError(f"duplicate official plugin id in catalog policy: {plugin_id}")

        sources = int(isinstance(repository, str)) + int(isinstance(source_catalog, str))
        if sources != 1:
            raise CatalogError(
                f"official plugin {plugin_id!r} must declare exactly one trusted repository or source_catalog"
            )
        if isinstance(repository, str) and REPOSITORY_RE.fullmatch(repository) is None:
            raise CatalogError(f"official plugin {plugin_id!r} has an invalid repository")
        if isinstance(source_catalog, str) and not source_catalog.startswith(("https://", "http://")):
            raise CatalogError(f"official plugin {plugin_id!r} has an invalid source_catalog")

        normalized_entry = {"plugin": plugin_id}
        if isinstance(repository, str):
            normalized_entry["repository"] = repository
        else:
            assert isinstance(source_catalog, str)
            normalized_entry["source_catalog"] = source_catalog
        normalized.append(normalized_entry)
        seen_ids.add(plugin_id)

    return {"official": normalized}


def pin_raw_github_base(client: GitHubClient, base: str) -> str:
    match = RAW_GITHUB_BASE_RE.fullmatch(base)
    if match is None:
        return base

    owner, repo, remainder = match.groups()
    parts = [part for part in remainder.split("/") if part]
    if len(parts) < 2:
        return base

    if len(parts) >= 3 and parts[0] == "refs" and parts[1] == "heads":
        ref = parts[2]
        subpath_parts = parts[3:]
    else:
        ref = parts[0]
        subpath_parts = parts[1:]

    if re.fullmatch(r"[0-9a-fA-F]{40}", ref):
        sha = ref.lower()
    else:
        sha = client.commit_sha(f"{owner}/{repo}", ref)

    suffix = "/".join(subpath_parts)
    if suffix:
        suffix += "/"
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{sha}/{suffix}"


def curated_catalog_plugins(
    client: GitHubClient,
    whitelist: dict[str, Any],
    blacklisted_repositories: set[str] | None = None,
) -> list[dict[str, Any]]:
    imported: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    blacklisted = blacklisted_repositories or set()

    for source in whitelist.get("catalogs", []):
        url = source.get("url")
        plugin_ids = source.get("plugins")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            raise CatalogError("whitelist catalog url must be http(s)")
        if is_blacklisted_repository(github_repository_from_url(url), blacklisted):
            continue
        if not isinstance(plugin_ids, list) or not all(
            isinstance(item, str) and PLUGIN_ID_RE.fullmatch(item) for item in plugin_ids
        ):
            raise CatalogError(f"whitelist plugin ids are invalid for {url}")

        payload = client.fetch_json_url(url)
        source_plugins = payload.get("plugins")
        if not isinstance(source_plugins, list):
            raise CatalogError(f"catalog has no plugins list: {url}")

        by_id = {
            item.get("name"): item
            for item in source_plugins
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }

        for plugin_id in plugin_ids:
            if plugin_id in seen_ids:
                raise CatalogError(f"duplicate whitelisted plugin id: {plugin_id}")
            source_entry = by_id.get(plugin_id)
            if not isinstance(source_entry, dict):
                raise CatalogError(f"whitelisted plugin {plugin_id!r} not found in {url}")

            version_value = source_entry.get("version")
            base = source_entry.get("base")
            files_value = source_entry.get("files")
            if not isinstance(version_value, str) or normalize_version(version_value) is None:
                raise CatalogError(f"whitelisted plugin {plugin_id!r} has invalid version")
            if not isinstance(base, str) or not base.startswith(("https://", "http://")):
                raise CatalogError(f"whitelisted plugin {plugin_id!r} has invalid base")
            files = safe_runtime_files({"files": files_value}, set())
            if files is None:
                raise CatalogError(f"whitelisted plugin {plugin_id!r} has invalid files")

            title = source_entry.get("title")
            description = source_entry.get("description")
            author = source_entry.get("author")
            imported.append(
                {
                    "name": plugin_id,
                    "title": title if isinstance(title, str) and title else plugin_id,
                    "description": description if isinstance(description, str) else "",
                    "author": author if isinstance(author, str) else "",
                    "version": normalize_version(version_value),
                    "source_catalog": url,
                    "base": pin_raw_github_base(client, base),
                    "files": files,
                }
            )
            seen_ids.add(plugin_id)

    imported.sort(key=lambda item: (item["title"].casefold(), item["name"]))
    return imported


def matching_release_assets(release: dict[str, Any]) -> list[dict[str, Any]]:
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise CatalogError("GitHub release assets must be a list")
    matching = [
        asset
        for asset in assets
        if isinstance(asset, dict)
        and isinstance(asset.get("name"), str)
        and asset["name"].lower().endswith(RELEASE_ASSET_SUFFIX)
    ]
    return sorted(matching, key=lambda asset: asset["name"].casefold())


def _safe_archive_member_name(name: str) -> str | None:
    candidate = name[:-1] if name.endswith("/") else name
    if not candidate or candidate.startswith("/") or "\\" in candidate:
        return None
    parts = candidate.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    return candidate


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    if info.create_system != 3:
        return False
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def inspect_release_asset(
    archive_bytes: bytes,
    repository: str,
    asset_name: str,
) -> tuple[dict[str, Any], list[str], dict[str, bytes]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise CatalogError(f"{repository} asset {asset_name!r} is not a valid ZIP") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise CatalogError(
                f"{repository} asset {asset_name!r} has too many archive members"
            )

        members: dict[str, zipfile.ZipInfo] = {}
        casefolded: set[str] = set()
        total_uncompressed = 0
        for info in infos:
            safe_name = _safe_archive_member_name(info.filename)
            if safe_name is None:
                raise CatalogError(
                    f"{repository} asset {asset_name!r} contains an unsafe path {info.filename!r}"
                )
            if info.flag_bits & 0x1:
                raise CatalogError(
                    f"{repository} asset {asset_name!r} contains encrypted files"
                )
            if _is_zip_symlink(info):
                raise CatalogError(
                    f"{repository} asset {asset_name!r} contains a symbolic link"
                )
            if info.is_dir():
                continue
            folded = safe_name.casefold()
            if safe_name in members or folded in casefolded:
                raise CatalogError(
                    f"{repository} asset {asset_name!r} contains duplicate paths"
                )
            members[safe_name] = info
            casefolded.add(folded)
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise CatalogError(
                    f"{repository} asset {asset_name!r} is too large after extraction"
                )

        candidates: list[tuple[str, str]] = []
        for path in members:
            if path == "manifest.json":
                root = ""
            elif path.endswith("/manifest.json"):
                root = path[: -len("manifest.json")]
            else:
                continue
            if f"{root}device.json" in members or f"{root}plugin.js" in members:
                candidates.append((path, root))

        if len(candidates) != 1:
            raise CatalogError(
                f"{repository} asset {asset_name!r} must contain exactly one CrossPoint plugin root"
            )

        manifest_path, root = candidates[0]
        manifest_info = members[manifest_path]
        if manifest_info.file_size > MAX_PLUGIN_FILE_BYTES:
            raise CatalogError(
                f"{repository} asset {asset_name!r} manifest is unexpectedly large"
            )
        try:
            manifest = json.loads(archive.read(manifest_info).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise CatalogError(
                f"{repository} asset {asset_name!r} has an invalid manifest.json"
            ) from exc
        if not isinstance(manifest, dict):
            raise CatalogError(
                f"{repository} asset {asset_name!r} manifest.json must be an object"
            )

        manifest_version = manifest.get("version")
        if not isinstance(manifest_version, str) or normalize_version(manifest_version) is None:
            raise CatalogError(
                f"{repository} asset {asset_name!r} has an invalid manifest version"
            )

        plugin_id = manifest.get("name")
        if not isinstance(plugin_id, str) or PLUGIN_ID_RE.fullmatch(plugin_id) is None:
            root_name = root.rstrip("/").split("/")[-1] if root else ""
            plugin_id = derive_plugin_id(root_name, {}) if root_name else None
            if plugin_id is None:
                raise CatalogError(
                    f"{repository} asset {asset_name!r} must declare a safe manifest name "
                    "or use a safe plugin directory name"
                )
            manifest = dict(manifest)
            manifest["name"] = plugin_id

        relative_members = {
            path[len(root) :]
            for path in members
            if path.startswith(root) and len(path) > len(root)
        }
        root_names = {path for path in relative_members if "/" not in path}
        files = safe_runtime_files(manifest, root_names)
        if files is None:
            raise CatalogError(
                f"{repository} asset {asset_name!r} manifest files are missing or unsafe"
            )

        payloads: dict[str, bytes] = {}
        total_plugin_bytes = 0
        for relative_path in files:
            member_path = f"{root}{relative_path}"
            info = members.get(member_path)
            if info is None:
                raise CatalogError(
                    f"{repository} asset {asset_name!r} is missing declared file {relative_path!r}"
                )
            if info.file_size > MAX_PLUGIN_FILE_BYTES:
                raise CatalogError(
                    f"{repository} asset {asset_name!r} file {relative_path!r} is too large"
                )
            total_plugin_bytes += info.file_size
            if total_plugin_bytes > MAX_PLUGIN_TOTAL_BYTES:
                raise CatalogError(
                    f"{repository} asset {asset_name!r} plugin payload is too large"
                )
            payloads[relative_path] = archive.read(info)

    return manifest, files, payloads


def mirror_plugin_payload(
    mirror_root: Path,
    plugin_id: str,
    version: str,
    payloads: dict[str, bytes],
) -> Path:
    target = mirror_root / plugin_id / version
    if target.exists():
        existing = {
            path.relative_to(target).as_posix(): path.read_bytes()
            for path in target.rglob("*")
            if path.is_file()
        }
        if existing != payloads:
            raise CatalogError(
                f"refusing to rewrite mirrored {plugin_id} {version}; publish a new plugin version"
            )
        return target

    for relative_path, payload in payloads.items():
        destination = target.joinpath(*relative_path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    return target


def release_asset_plugins(
    client: GitHubClient,
    repositories: list[str],
    catalog_repository: str,
    mirror_root: Path,
    blacklisted_repositories: set[str] | None = None,
) -> list[dict[str, Any]]:
    if not repositories:
        return []
    if REPOSITORY_RE.fullmatch(catalog_repository) is None:
        raise CatalogError("catalog repository must be an owner/repository string")

    plugins: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    blacklisted = blacklisted_repositories or set()
    for full_name in repositories:
        if is_blacklisted_repository(full_name, blacklisted):
            continue
        repo = client.repository(full_name)
        if repo.get("archived") or repo.get("disabled"):
            raise CatalogError(f"configured release-asset repository is unavailable: {full_name}")

        selected_release: dict[str, Any] | None = None
        selected_assets: list[dict[str, Any]] = []
        for release in client.stable_releases(full_name):
            assets = matching_release_assets(release)
            if assets:
                selected_release = release
                selected_assets = assets
                break
        if selected_release is None:
            raise CatalogError(
                f"configured release-asset repository has no stable release containing *{RELEASE_ASSET_SUFFIX}: {full_name}"
            )

        tag = selected_release.get("tag_name")
        if not isinstance(tag, str) or not tag:
            raise CatalogError(f"selected GitHub release has no tag for {full_name}")

        for asset in selected_assets:
            asset_name = asset.get("name")
            download_url = asset.get("browser_download_url")
            if not isinstance(asset_name, str) or not isinstance(download_url, str):
                raise CatalogError(f"matching release asset metadata is incomplete for {full_name}")
            archive_bytes = client.fetch_bytes_url(download_url)
            manifest, files, payloads = inspect_release_asset(
                archive_bytes,
                full_name,
                asset_name,
            )
            plugin_id = manifest["name"]
            version = normalize_version(manifest["version"])
            assert version is not None
            if plugin_id in seen_ids:
                raise CatalogError(
                    f"duplicate plugin id {plugin_id!r} across configured release assets"
                )
            seen_ids.add(plugin_id)

            mirror_plugin_payload(mirror_root, plugin_id, version, payloads)
            mirror_rel = f"{RELEASE_ASSET_MIRROR_DIR}/{plugin_id}/{version}/"
            title = manifest.get("title")
            description = manifest.get("description")
            author = manifest.get("author")
            plugins.append(
                {
                    "name": plugin_id,
                    "title": title if isinstance(title, str) and title else plugin_id,
                    "description": (
                        description
                        if isinstance(description, str)
                        else (repo.get("description") or "")
                    ),
                    "author": (
                        author
                        if isinstance(author, str)
                        else repo.get("owner", {}).get("login", "")
                    ),
                    "version": version,
                    "repository": full_name,
                    "release": tag,
                    "release_url": selected_release.get("html_url", ""),
                    "release_asset": asset_name,
                    "published_at": selected_release.get("published_at", ""),
                    "base": (
                        f"https://raw.githubusercontent.com/{catalog_repository}/main/"
                        f"{urllib.parse.quote(mirror_rel, safe='/')}"
                    ),
                    "files": files,
                }
            )

    plugins.sort(key=lambda item: (item["title"].casefold(), item["name"]))
    return plugins


def _matches_official_source(plugin: dict[str, Any], policy_entry: dict[str, str]) -> bool:
    repository = policy_entry.get("repository")
    if repository is not None:
        candidate_repository = plugin.get("repository")
        return isinstance(candidate_repository, str) and candidate_repository.lower() == repository.lower()

    source_catalog = policy_entry.get("source_catalog")
    return isinstance(source_catalog, str) and plugin.get("source_catalog") == source_catalog


def split_plugins_by_policy(
    release_plugins: list[dict[str, Any]],
    curated_plugins: list[dict[str, Any]],
    asset_plugins: list[dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: dict[str, list[dict[str, Any]]] = {}
    for plugin in [*curated_plugins, *release_plugins, *asset_plugins]:
        candidates.setdefault(plugin["name"], []).append(plugin)

    official_policy = {
        entry["plugin"]: entry
        for entry in policy.get("official", [])
    }
    official: list[dict[str, Any]] = []
    community: list[dict[str, Any]] = []

    for plugin_id, entries in candidates.items():
        policy_entry = official_policy.get(plugin_id)
        if policy_entry is not None:
            trusted = [entry for entry in entries if _matches_official_source(entry, policy_entry)]
            if len(trusted) != 1:
                raise CatalogError(
                    f"official plugin {plugin_id!r} must resolve to exactly one trusted source; found {len(trusted)}"
                )
            if len(entries) > 1:
                ignored = len(entries) - 1
                print(
                    f"official plugin {plugin_id!r}: ignored {ignored} conflicting untrusted candidate"
                    + ("s" if ignored != 1 else ""),
                    file=sys.stderr,
                )
            official.append(trusted[0])
            continue

        if len(entries) != 1:
            raise CatalogError(
                f"duplicate community plugin id {plugin_id!r} across {len(entries)} sources"
            )
        community.append(entries[0])

    missing = sorted(set(official_policy) - set(candidates))
    if missing:
        raise CatalogError("official plugins missing from discovered inputs: " + ", ".join(missing))

    sort_key = lambda item: (item["title"].casefold(), item["name"])
    official.sort(key=sort_key)
    community.sort(key=sort_key)
    return official, community


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
        print(f"skip {full_name}: release tag {tag!r} is not a three-part numeric version", file=sys.stderr)
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
    excluded_repositories: set[str] | None = None,
    max_repositories: int | None = None,
    included_repositories: list[str] | None = None,
) -> list[dict[str, Any]]:
    blacklisted = excluded_repositories or set()
    discovered: dict[str, dict[str, Any]] = {}
    for query in SEARCH_QUERIES:
        for repo in client.search_repositories(query):
            full_name = repo.get("full_name")
            if not isinstance(full_name, str):
                continue
            key = full_name.lower()
            if key not in discovered:
                discovered[key] = repo

    for full_name in included_repositories or []:
        if is_blacklisted_repository(full_name, blacklisted):
            continue
        key = full_name.lower()
        if key not in discovered:
            discovered[key] = client.repository(full_name)

    plugins: list[dict[str, Any]] = []
    for repo in discovered.values():
        full_name = repo.get("full_name", "")
        if is_blacklisted_repository(full_name, blacklisted):
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


def write_catalog(
    path: Path,
    plugins: list[dict[str, Any]],
    name: str = "Plugin Hub",
) -> bool:
    existing = load_existing(path)
    old_plugins = existing.get("plugins")
    old_name = existing.get("name")
    generated_at = existing.get("generated_at")
    changed = old_plugins != plugins or old_name != name
    if changed or not isinstance(generated_at, str):
        generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    payload = {
        "name": name,
        "schema_version": 1,
        "generated_at": generated_at,
        "plugins": plugins,
    }
    rendered = compact_json(payload)
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    if previous == rendered:
        return False
    path.write_text(rendered, encoding="utf-8", newline="\n")
    return True


def write_list_index(path: Path, lists: list[dict[str, Any]]) -> bool:
    existing = load_existing(path)
    generated_at = existing.get("generated_at")
    changed = existing.get("lists") != lists
    if changed or not isinstance(generated_at, str):
        generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {"schema_version": 1, "generated_at": generated_at, "lists": lists}
    rendered = compact_json(payload)
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    if previous == rendered:
        return False
    path.write_text(rendered, encoding="utf-8", newline="\n")
    return True


def write_community_catalogs(
    community_path: Path,
    index_path: Path,
    official_path: Path,
    plugins: list[dict[str, Any]],
    repository: str,
    ref: str,
    max_bytes: int,
) -> dict[str, bool]:
    try:
        partitions = partition_community_plugins(plugins, max_bytes)
    except ValueError as exc:
        raise CatalogError(str(exc)) from exc

    changes: dict[str, bool] = {}
    desired: set[Path] = set()
    for partition in partitions:
        filename = shard_filename(community_path.name, partition)
        path = community_path.with_name(filename)
        desired.add(path)
        key = "community" if not partition.label else f"community-{partition.label.lower()}"
        changes[key] = write_catalog(path, partition.plugins, partition.title)

    stale_candidates = set(community_path.parent.glob(f"{community_path.stem}-*{community_path.suffix}"))
    stale_candidates.add(community_path)
    for stale in sorted(stale_candidates - desired):
        if stale.exists():
            stale.unlink()
            changes[f"removed-{stale.name}"] = True

    lists = list_index_entries(repository, ref, official_path.name, community_path.name, partitions)
    changes["list-index"] = write_list_index(index_path, lists)
    return changes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="catalog.json", help="compatibility union catalog path")
    parser.add_argument("--official-output", default="official-catalog.json", help="official catalog path")
    parser.add_argument("--community-output", default="community-catalog.json", help="community catalog path")
    parser.add_argument("--list-index-output", default=COMMUNITY_LIST_INDEX, help="dynamic native catalog list index path")
    parser.add_argument("--catalog-ref", default=os.environ.get("PLUGINHUB_CATALOG_REF", "main"), help="git ref used by generated raw catalog URLs")
    parser.add_argument("--community-max-bytes", type=int, default=COMMUNITY_CATALOG_MAX_BYTES, help="maximum serialized bytes per Community catalog shard")
    parser.add_argument("--whitelist", default="whitelist.json", help="curated plugin whitelist")
    parser.add_argument("--blacklist", default="blacklist.json", help="repositories omitted from all generated catalogs")
    parser.add_argument("--policy", default="catalog-policy.json", help="catalog classification policy")
    parser.add_argument(
        "--exclude-repository",
        default=None,
        help="optional additional owner/repository to exclude for this run",
    )
    parser.add_argument(
        "--catalog-repository",
        default=os.environ.get("GITHUB_REPOSITORY", "jadehawk/PluginHub.crosspoint-plugin"),
        help="owner/repository used for generated release-asset mirror URLs",
    )
    parser.add_argument("--max-repositories", type=int, default=None, help="optional accepted-plugin limit for testing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    client = GitHubClient(token)
    try:
        whitelist = load_whitelist(Path(args.whitelist))
        blacklist = load_blacklist(Path(args.blacklist))
        blacklisted_repositories = {repository.lower() for repository in blacklist["repositories"]}
        if args.exclude_repository:
            if REPOSITORY_RE.fullmatch(args.exclude_repository) is None:
                raise CatalogError("exclude-repository must be an owner/repository string")
            blacklisted_repositories.add(args.exclude_repository.lower())
        policy = filter_blacklisted_policy(load_policy(Path(args.policy)), blacklisted_repositories)
        release_plugins = discover_plugins(
            client,
            blacklisted_repositories,
            args.max_repositories,
            whitelist.get("repositories", []),
        )
        asset_plugins = release_asset_plugins(
            client,
            whitelist.get("release_asset_repositories", []),
            args.catalog_repository,
            Path(RELEASE_ASSET_MIRROR_DIR),
            blacklisted_repositories,
        )
        curated_plugins = curated_catalog_plugins(client, whitelist, blacklisted_repositories)
        official_plugins, community_plugins = split_plugins_by_policy(
            release_plugins,
            curated_plugins,
            asset_plugins,
            policy,
        )
        official_plugins = [
            plugin for plugin in official_plugins if not plugin_entry_is_blacklisted(plugin, blacklisted_repositories)
        ]
        community_plugins = [
            plugin for plugin in community_plugins if not plugin_entry_is_blacklisted(plugin, blacklisted_repositories)
        ]
        plugins = sorted(
            [*official_plugins, *community_plugins],
            key=lambda item: (item["title"].casefold(), item["name"]),
        )
    except CatalogError as exc:
        print(f"catalog build failed: {exc}", file=sys.stderr)
        return 1

    official_path = Path(args.official_output)
    changes = {
        "compatibility": write_catalog(Path(args.output), plugins, "Plugin Hub"),
        "official": write_catalog(official_path, official_plugins, "Official Plugins"),
    }
    try:
        changes.update(
            write_community_catalogs(
                Path(args.community_output),
                Path(args.list_index_output),
                official_path,
                community_plugins,
                args.catalog_repository,
                args.catalog_ref,
                args.community_max_bytes,
            )
        )
    except CatalogError as exc:
        print(f"catalog build failed: {exc}", file=sys.stderr)
        return 1
    changed_names = [name for name, changed in changes.items() if changed]
    print(
        f"catalogs {'updated: ' + ', '.join(changed_names) if changed_names else 'unchanged'}; "
        f"{len(official_plugins)} official, {len(community_plugins)} community, {len(plugins)} total "
        f"({len(release_plugins)} release-discovered, {len(asset_plugins)} release-asset, "
        f"{len(curated_plugins)} curated)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
