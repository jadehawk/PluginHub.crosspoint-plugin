# Plugin Hub catalog and firmware reference

This document is the maintainer reference for Plugin Hub catalog generation, Official/Community classification, repository allow/deny controls, the CrossPoint firmware support required by Plugin Hub 0.1.6, and the large-catalog torture testing used before release.

## Release status: Plugin Hub 0.1.6 is intentionally on standby

Plugin Hub `0.1.6` is ready on `main`, but it must not become the stable Plugin Hub release until the matching CrossPoint firmware support is merged and available to users.

Production remains:

- `stable` branch: Plugin Hub 0.1.5
- latest stable GitHub Release: `v0.1.5`
- firmware Settings -> Install Plugin Hub: downloads from `stable`, so normal users continue to receive 0.1.5
- Plugin Hub's own Official catalog entry: resolves from the latest stable GitHub Release, so it continues to advertise 0.1.5 until `v0.1.6` is published

Why the gate exists: 0.1.6 replaces the old static native Official/Community list definition with `browse.lists_url`. Older plugin-enabled firmware does not understand `lists_url`, so the native Plugin Hub catalog picker requires the firmware changes described below. The browser WebUI can fetch the dynamic list index itself, but native on-device browsing is the release blocker.

After the firmware change is merged/released, publish `v0.1.6`. The stable-promotion workflow can then move `stable` to 0.1.6, the catalog refresh will advertise 0.1.6, and existing 0.1.5 users can update Plugin Hub through the normal plugin bundle updater.

## Catalog sources and classification

Catalog generation is intentionally split into three separate decisions:

1. **Discovery / ingestion**: where candidates come from.
2. **Blacklist**: which repositories must never be published.
3. **Official policy**: which surviving plugin IDs and trusted sources are Official.

Anything valid that survives the blacklist and is not explicitly Official becomes Community.

### Automatic discovery

The recommended path requires no Plugin Hub pull request. The GitHub Action searches public repositories using:

- GitHub topic `crosspoint-plugin`
- repository-name compatibility search for `crosspoint-plugin`

A standalone plugin must have a stable, non-draft, non-prerelease GitHub Release, a matching three-part version in `manifest.json`, and installable runtime files.

### `whitelist.json`

`whitelist.json` is for sources that cannot use normal automatic discovery. It is not the Official list.

Example:

```json
{
  "repositories": [
    "owner/standalone-exception"
  ],
  "release_asset_repositories": [
    "owner/monorepo"
  ],
  "catalogs": [
    {
      "url": "https://raw.githubusercontent.com/owner/catalog/main/catalog.json",
      "plugins": [
        "plugin-one",
        "plugin-two"
      ]
    }
  ]
}
```

Meaning:

- `repositories`: manually include a standalone GitHub repository, while still requiring the normal release/manifest validation.
- `release_asset_repositories`: inspect stable Releases for `*.crosspoint-plugin.zip` assets and publish valid plugin packages found there.
- `catalogs`: import only the explicitly named plugin IDs from another catalog. Plugin Hub never imports an entire external catalog implicitly.

Prefer fixing a new plugin to follow the automatic repository convention instead of adding it to the whitelist.

### `blacklist.json`

`blacklist.json` is the repository-level deny list.

Example:

```json
{
  "repositories": [
    "owner/repository-to-block",
    "another-owner/another-repository"
  ]
}
```

Repository matching is case-insensitive.

**Blacklist wins over every other catalog source or classification.** A blacklisted repository is omitted even if it:

- is found through automatic GitHub discovery
- appears in `whitelist.json -> repositories`
- appears in `whitelist.json -> release_asset_repositories`
- hosts a curated GitHub catalog
- is the GitHub repository behind a curated plugin's `base` URL
- is named as the trusted source of an Official plugin in `catalog-policy.json`

This is intentionally stronger than the old special-case self-exclusion. Plugin Hub itself is not blacklisted.

### `catalog-policy.json`

`catalog-policy.json` controls Official status. Official entries must identify one trusted source.

Repository-backed example:

```json
{
  "plugin": "pluginhub",
  "repository": "jadehawk/PluginHub.crosspoint-plugin"
}
```

Curated-catalog-backed example:

```json
{
  "plugin": "bookfusion",
  "source_catalog": "https://raw.githubusercontent.com/itsthisjustin/sd-plugins/main/catalog.json"
}
```

If an Official plugin ID is also claimed by an untrusted source, the trusted policy source wins. Duplicate Community IDs fail the catalog refresh instead of silently selecting a winner.

Plugin Hub itself is intentionally Official. Once a future stable Plugin Hub Release is newer than the installed copy, the normal catalog updater can update Plugin Hub in place.

## Generated catalogs

The refresh workflow runs every three hours and can also be triggered manually. It validates sources, applies blacklist/policy rules, and emits compact JSON.

Generated files include:

- `catalog.json` - backward-compatible union of Official + Community
- `official-catalog.json` - Official plugins only
- `community-catalog.json` - Community plugins when one file fits
- `community-catalog-<range>.json` - automatically generated Community shards when splitting is required
- `catalog-lists.json` - live native/WebUI index of the currently generated user-facing lists

Machine-generated catalog JSON is compact/minified before byte-size decisions are made.

## Dynamic Community catalog splitting

CrossPoint's native catalog reader has a 1 MiB browse-response safety limit. Plugin Hub therefore measures the **actual compact serialized UTF-8 byte size**, not plugin count.

Behavior:

1. If the full Community catalog fits below 1 MiB, generate one `community-catalog.json`.
2. If it does not fit, group plugins by first title letter and find the minimum number of contiguous alphabetical shards that each fit below the limit.
3. Among solutions using the minimum shard count, prefer a balanced split that minimizes the largest shard.
4. Do not split one first-letter bucket across two shards.
5. Generate deterministic names such as `community-catalog-a-m.json` and `community-catalog-n-z.json`.
6. Remove stale shard files when the required split changes on a later refresh.
7. Regenerate `catalog-lists.json` so clients immediately see the new shard layout without a Plugin Hub release.

If a future single first-letter bucket itself exceeds 1 MiB, the current generator stops with an error rather than silently producing an oversized native catalog. That case has not been approached in current testing.

## `catalog-lists.json`

`catalog-lists.json` is the indirection that allows the catalog layout to change without changing `device.json` or releasing Plugin Hub again.

Normal shape:

```json
{
  "schema_version": 1,
  "generated_at": "...",
  "lists": [
    {
      "title": "Official Plugins",
      "url": "https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/official-catalog.json"
    },
    {
      "title": "Community Plugins",
      "url": "https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/community-catalog.json",
      "notice": {
        "title": "Community Plugins",
        "message": "Third-party plugins. Not vetted by Dev Team.",
        "confirm": "Continue",
        "cancel": "Go Back"
      }
    }
  ]
}
```

When Community is split, the same index simply contains multiple Community entries with range labels. No Plugin Hub release is needed merely because the Action changed the number of shards.

## Community warning / confirmation

Every Community list or shard carries the same notice:

- title: `Community Plugins`
- message: `Third-party plugins. Not vetted by Dev Team.`
- confirm: `Continue`
- cancel: `Go Back`

The notice is data in `catalog-lists.json`; the firmware enhancement makes the generic native catalog picker display it. Cancel returns to the list picker. Confirm opens the selected Community catalog.

This is generic firmware functionality, not hard-coded Plugin Hub UI, so other plugins can attach notices to named catalog lists as well.

## CrossPoint firmware enhancements used by Plugin Hub 0.1.6

The full firmware feature work is committed and pushed on `feat/install-plugin-hub-settings` as `e88581e7` (`feat: add dynamic plugin catalog lists and notices`), on top of the original installer commit `d8ba9499`. The native **Install Plugin Hub** change was physically validated on X3, X4, X4Pro, and Seeed reTerminal Sticky, and the later dynamic-list / notice extensions were tested with the 2K/4K/6K catalog torture scenarios described below. Plugin Hub 0.1.6 must wait until these firmware changes are merged/released.

### 1. Settings -> Install Plugin Hub

A firmware-native `PluginHubInstallActivity` adds **Install Plugin Hub** under Settings when Plugin Hub is not already installed.

It:

- checks all supported plugin roots to determine whether Plugin Hub is already installed
- asks for confirmation before installation
- connects Wi-Fi using the normal catalog flow
- downloads the four runtime files from the Plugin Hub `stable` branch:
  - `manifest.json`
  - `device.json`
  - `plugin.js`
  - `README.md`
- stages every download as `*.new`
- replaces the live files only after every runtime file downloaded successfully
- removes staged files after failure so retry is safe
- leaves `stable` as the production control point, allowing `main` to move ahead without exposing unreleased Plugin Hub code to normal users

### 2. Remote named-list index: `browse.lists_url`

Firmware `PluginCatalogActivity` gains an optional `browse.lists_url` manifest field.

When present, firmware:

- fetches the remote list index before showing the list picker
- caps that small index response at 16 KiB
- parses each entry's `title`, `url`, optional `body`, and optional `notice`
- ignores invalid list entries without a usable title+URL
- fails the browse operation cleanly if the remote index cannot be fetched or contains no valid lists
- retries through the list-index loading path when appropriate

This allows Plugin Hub's GitHub Action to add/remove Community shards dynamically without changing or releasing the plugin.

Plugin Hub 0.1.6 intentionally uses `lists_url` without a static `browse.lists` fallback because this feature has not yet been released; 0.1.6 is being held until supporting firmware exists.

### 3. Generic per-list notices

Firmware named lists now understand:

```json
"notice": {
  "title": "Community Plugins",
  "message": "Third-party plugins. Not vetted by Dev Team.",
  "confirm": "Continue",
  "cancel": "Go Back"
}
```

A notice appears before the list is opened. The implementation is generic and can be reused by other catalog plugins.

### 4. Custom confirmation button labels

`ConfirmationActivity` was extended to accept optional cancel/confirm labels. Existing callers continue using translated default Cancel/Confirm labels when custom labels are omitted.

Plugin Hub uses this to show `Go Back` and `Continue` for the Community warning rather than generic confirmation wording.

### 5. Existing generic plugin-catalog behavior this design relies on

These are important parts of the firmware plugin system that make Plugin Hub work safely and should be preserved when porting the feature:

- named JSON catalog lists and a native list-picker UI
- native paging with a bounded page size
- streaming large browse responses to SD rather than retaining the entire catalog in RAM
- 1 MiB maximum native browse response
- installed-version lookup from plugin `manifest.json`
- update badge only when the catalog version is newer, avoiding downgrade prompts
- plugin lookup across all supported plugin roots
- bundle installation under `/.crosspoint/plugins/<id>/`
- per-file `*.new` staging before replacement during bundle installs
- cleanup on failed/cancelled bundle downloads
- plugin event-subscription refresh after a plugin bundle is installed or updated
- rescanning installed plugins when reopening the plugin picker, so a newly installed plugin becomes visible without a firmware reboot

Plugin Hub self-update is safe in the native catalog UI because the active catalog screen is firmware code. Updating Plugin Hub replaces its SD-card files; the new Plugin Hub code is used the next time it is opened.

## Browser WebUI support for large catalogs

The browser-side `plugin.js` also consumes `catalog-lists.json` dynamically.

The normal relay endpoint has a much smaller response-body limit than the native catalog response. When a catalog is too large for `/api/relay`, Plugin Hub falls back to the firmware fetch-to-SD API, reads the temporary downloaded catalog through `/download`, and deletes the temporary cache file afterward.

This keeps the WebUI usable with the same large shards used by the native UI.

## 2K / 4K / 6K torture test

Large-catalog testing is reproducible from `tools/generate_stress_test_catalogs.py` and the committed `stress/` fixtures.

The test uses real Plugin Hub catalog entries as templates, duplicates them into realistic action-style plugin records, assigns deterministic A-Z titles, then runs the same production partitioner used by catalog generation.

Tested output:

| Scenario | Shard | Plugins | Serialized size |
| --- | --- | ---: | ---: |
| 2K | `community-catalog.json` | 2,000 | 901,750 bytes |
| 4K | `community-catalog-a-m.json` | 2,002 | 902,643 bytes |
| 4K | `community-catalog-n-z.json` | 1,998 | 900,793 bytes |
| 6K | `community-catalog-a-h.json` | 1,848 | 833,217 bytes |
| 6K | `community-catalog-i-q.json` | 2,079 | 937,356 bytes |
| 6K | `community-catalog-r-z.json` | 2,073 | 934,572 bytes |

All individual shards remained below the firmware's 1 MiB response limit.

Physical-device result with the test firmware and Plugin Hub 0.1.6:

- 2K catalog opened successfully and paginated
- both 4K shards opened successfully and paginated
- all three 6K shards opened successfully and paginated
- the remote dynamic list index loaded correctly
- Community notice/confirmation displayed correctly
- switching between the generated stress-list entries required no firmware or Plugin Hub reinstall

This is deliberately far beyond the expected near-term CrossPoint plugin count and serves as an extreme regression test for list-index loading, response-size partitioning, SD-backed parsing, and native pagination.

### Reproducing the stress fixtures

From the repository root:

```text
python tools/generate_stress_test_catalogs.py
```

The generator should be treated as test tooling. It writes its test index to `stress/catalog-lists.json`; production `catalog-lists.json` must point only to the normal Official/Community generated catalogs on `main`. The committed stress index can be used by a temporary test build without touching the production index.

The exact byte sizes above describe the committed fixtures that were physically tested. Regenerating later may change sizes slightly if the real catalog entries used as templates have changed, but the same production partitioner and 1 MiB limit are used.

## Release checklist for 0.1.6

Before publishing `v0.1.6`:

1. Merge/release the CrossPoint firmware support for `browse.lists_url` and per-list notices.
2. Confirm the target firmware can open Official and Community from the production `catalog-lists.json`.
3. Confirm `stable` still points to 0.1.5 until the actual 0.1.6 release is intentionally published.
4. Confirm `device.json` and generated catalog URLs use `main`, not a temporary test branch.
5. Run Python catalog tests and browser plugin tests.
6. Run the 2K/4K/6K stress generator when catalog/partition logic changes materially.
7. Publish stable GitHub Release `v0.1.6`.
8. Let the stable-promotion workflow advance `stable` to the release.
9. Confirm the next catalog refresh publishes Plugin Hub 0.1.6 in Official Plugins and offers an update to installed 0.1.5 copies.

## Files to reference

Plugin Hub repository:

- `tools/build_catalog.py` - discovery, validation, blacklist/policy application, catalog generation
- `tools/catalog_partitions.py` - compact serialization and Community partition algorithm
- `tools/generate_stress_test_catalogs.py` - 2K/4K/6K stress fixture generator
- `whitelist.json` - exceptional/manual ingestion sources
- `blacklist.json` - repository deny list
- `catalog-policy.json` - Official plugin trusted-source policy
- `catalog-lists.json` - current generated user-facing list index
- `device.json` - native catalog manifest using `browse.lists_url`
- `plugin.js` - browser UI and large-catalog fallback

Firmware feature reference:

- `src/activities/settings/PluginHubInstallActivity.cpp/.h`
- `src/activities/settings/SettingsActivity.cpp/.h`
- `src/activities/plugins/PluginCatalogActivity.cpp/.h`
- `src/activities/util/ConfirmationActivity.cpp/.h`
- `docs/sd-plugins.md`
