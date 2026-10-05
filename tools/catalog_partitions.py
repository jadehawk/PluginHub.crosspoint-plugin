from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

COMMUNITY_CATALOG_MAX_BYTES = 1024 * 1024
COMMUNITY_LIST_INDEX = "catalog-lists.json"
COMMUNITY_NOTICE = {
    "title": "Community Plugins",
    "message": "Third-party plugins. Not vetted by Dev Team.",
    "confirm": "Continue",
    "cancel": "Go Back",
}
_FIXED_TIMESTAMP = "2000-01-01T00:00:00Z"


@dataclass(frozen=True)
class CommunityPartition:
    label: str
    plugins: list[dict[str, Any]]

    @property
    def title(self) -> str:
        return "Community Plugins" if not self.label else f"Community Plugins [{self.label}]"


def compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def rendered_catalog_size(plugins: list[dict[str, Any]], name: str) -> int:
    payload = {
        "name": name,
        "schema_version": 1,
        "generated_at": _FIXED_TIMESTAMP,
        "plugins": plugins,
    }
    return len(compact_json(payload).encode("utf-8"))


def _bucket(plugin: dict[str, Any]) -> str:
    value = str(plugin.get("title") or plugin.get("name") or "").strip()
    if value and value[0].isascii() and value[0].isalpha():
        return value[0].upper()
    return "#"


def _range_label(first: str, last: str) -> str:
    return first if first == last else f"{first}-{last}"


def partition_community_plugins(
    plugins: list[dict[str, Any]],
    max_bytes: int = COMMUNITY_CATALOG_MAX_BYTES,
) -> list[CommunityPartition]:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    plugins = sorted(
        plugins,
        key=lambda plugin: (
            _bucket(plugin),
            str(plugin.get("title") or plugin.get("name") or "").casefold(),
            str(plugin.get("name") or ""),
        ),
    )
    if rendered_catalog_size(plugins, "Community Plugins") <= max_bytes:
        return [CommunityPartition("", plugins)]

    buckets: list[tuple[str, list[dict[str, Any]]]] = []
    for plugin in plugins:
        key = _bucket(plugin)
        if buckets and buckets[-1][0] == key:
            buckets[-1][1].append(plugin)
        else:
            buckets.append((key, [plugin]))

    group_plugins: dict[tuple[int, int], list[dict[str, Any]]] = {}
    group_sizes: dict[tuple[int, int], int] = {}
    for start in range(len(buckets)):
        combined: list[dict[str, Any]] = []
        for end in range(start, len(buckets)):
            combined.extend(buckets[end][1])
            label = _range_label(buckets[start][0], buckets[end][0])
            title = f"Community Plugins [{label}]"
            group_plugins[(start, end)] = list(combined)
            group_sizes[(start, end)] = rendered_catalog_size(combined, title)

    bucket_count = len(buckets)
    for part_count in range(2, bucket_count + 1):
        dp: list[list[int | None]] = [[None] * (bucket_count + 1) for _ in range(part_count + 1)]
        previous: list[list[int | None]] = [[None] * (bucket_count + 1) for _ in range(part_count + 1)]
        dp[0][0] = 0
        for used in range(1, part_count + 1):
            for end_exclusive in range(used, bucket_count + 1):
                for start in range(used - 1, end_exclusive):
                    prior = dp[used - 1][start]
                    if prior is None:
                        continue
                    candidate = max(prior, group_sizes[(start, end_exclusive - 1)])
                    current = dp[used][end_exclusive]
                    if current is None or candidate < current:
                        dp[used][end_exclusive] = candidate
                        previous[used][end_exclusive] = start
        if dp[part_count][bucket_count] is None or dp[part_count][bucket_count] > max_bytes:
            continue

        ranges: list[tuple[int, int]] = []
        end_exclusive = bucket_count
        used = part_count
        while used:
            start = previous[used][end_exclusive]
            if start is None:
                raise RuntimeError("failed to reconstruct Community catalog partitions")
            ranges.append((start, end_exclusive - 1))
            end_exclusive = start
            used -= 1
        ranges.reverse()
        return [
            CommunityPartition(
                _range_label(buckets[start][0], buckets[end][0]),
                group_plugins[(start, end)],
            )
            for start, end in ranges
        ]

    largest_size, largest_bucket = max(
        (rendered_catalog_size(items, f"Community Plugins [{label}]"), label)
        for label, items in buckets
    )
    raise ValueError(
        f"Community catalog cannot fit below {max_bytes} bytes without splitting the {largest_bucket!r} bucket "
        f"({largest_size} bytes)"
    )


def shard_filename(base_filename: str, partition: CommunityPartition) -> str:
    if not partition.label:
        return base_filename
    stem, dot, suffix = base_filename.rpartition(".")
    if not dot:
        stem, suffix = base_filename, ""
    slug = partition.label.lower().replace("#", "other")
    return f"{stem}-{slug}{dot}{suffix}"


def raw_catalog_url(repository: str, ref: str, filename: str) -> str:
    return f"https://raw.githubusercontent.com/{repository}/{ref}/{filename}"


def list_index_entries(
    repository: str,
    ref: str,
    official_filename: str,
    community_filename: str,
    partitions: list[CommunityPartition],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = [
        {
            "title": "Official Plugins",
            "url": raw_catalog_url(repository, ref, official_filename),
        }
    ]
    for partition in partitions:
        entries.append(
            {
                "title": partition.title,
                "url": raw_catalog_url(repository, ref, shard_filename(community_filename, partition)),
                "notice": dict(COMMUNITY_NOTICE),
            }
        )
    return entries
