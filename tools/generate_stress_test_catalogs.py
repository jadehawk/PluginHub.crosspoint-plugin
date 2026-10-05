from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

from catalog_partitions import COMMUNITY_NOTICE, compact_json, partition_community_plugins, shard_filename

REPOSITORY = "jadehawk/PluginHub.crosspoint-plugin"
BRANCH = "community-catalog-partitioning"
COUNTS = (2000, 4000, 6000)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    templates = json.loads((root / "catalog.json").read_text(encoding="utf-8"))["plugins"]
    generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    entries = [
        {
            "title": "Official Plugins",
            "url": f"https://raw.githubusercontent.com/{REPOSITORY}/{BRANCH}/official-catalog.json",
        }
    ]

    stress_root = root / "stress"
    stress_root.mkdir(exist_ok=True)

    for count in COUNTS:
        plugins = []
        for index in range(count):
            plugin = copy.deepcopy(templates[index % len(templates)])
            letter = chr(65 + (index % 26))
            plugin["name"] = f"{letter.lower()}-plugin-{index + 1:04d}"
            plugin["title"] = f"{letter} Plugin {index + 1:04d}"
            plugins.append(plugin)

        partitions = partition_community_plugins(plugins)
        scenario_dir = stress_root / str(count)
        scenario_dir.mkdir(parents=True, exist_ok=True)
        for old_file in scenario_dir.glob("*.json"):
            old_file.unlink()

        for partition in partitions:
            filename = shard_filename("community-catalog.json", partition)
            payload = {
                "name": partition.title,
                "schema_version": 1,
                "generated_at": generated_at,
                "plugins": partition.plugins,
            }
            path = scenario_dir / filename
            path.write_text(compact_json(payload), encoding="utf-8")
            entries.append(
                {
                    "title": f"TEST {count // 1000}K - {partition.title}",
                    "url": f"https://raw.githubusercontent.com/{REPOSITORY}/{BRANCH}/stress/{count}/{filename}",
                    "notice": dict(COMMUNITY_NOTICE),
                }
            )
            print(f"{path.relative_to(root).as_posix()}: {len(partition.plugins)} plugins, {path.stat().st_size} bytes")

    index_payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "lists": entries,
    }
    index_path = root / "catalog-lists.json"
    index_path.write_text(compact_json(index_payload), encoding="utf-8")
    print(f"catalog-lists.json: {len(entries)} lists, {index_path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
