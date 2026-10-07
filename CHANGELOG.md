# Changelog

## 0.1.6

- Compact generated catalogs and dynamically split oversized Community catalogs into balanced alphabetical ranges below the firmware-safe byte limit.
- Publish a dynamic catalog-list index so native Plugin Hub can follow Community catalog splits without requiring a plugin update.
- Add `blacklist.json`; repositories listed there are omitted from every generated catalog before whitelist or Official classification is applied.
- Add Plugin Hub itself to the Official catalog so installed copies can be updated through the normal catalog bundle update path.
- Reset automatic discovery to the folder-first repository standard: one plugin repository with exactly one direct child `<plugin-id>.crosspoint-plugin/` installable payload directory.
- Keep Plugin Hub itself as the intentional root-layout exception so its firmware bootstrap, root catalogs, and production `stable` branch remain unchanged.
- Add `PLUGIN_HUB_AGENT_GUIDE.md` so developers can hand the publishing contract directly to an AI coding agent.

## 0.1.5

- Split Plugin Hub into separate **Official Plugins** and **Community Plugins** feeds while retaining `catalog.json` as the backward-compatible union feed.
- Add explicit `catalog-policy.json` curation so Official status is tied to a plugin ID and trusted source instead of repository ownership or discovery order.
- Make trusted Official sources win conflicting claims and fail catalog generation on ambiguous duplicate Community plugin IDs.
- Add an on-reader Official/Community chooser through the firmware's existing `browse.lists` support, with no firmware-specific Plugin Hub changes required.
- Add a concise confirmation notice before opening **Community Plugins** so third-party plugins are clearly identified as not vetted by the Dev Team.
- Refactor the browser WebUI to browse one built-in catalog at a time, keep Official selected by default, and move custom/private catalogs into a secondary Custom catalogs section.
- Filter the legacy union and both built-in catalog URLs out of migrated custom-catalog settings so they cannot appear as duplicate user-facing choices.
- Add `PLUGIN_REPOSITORY_STANDARD.md` documenting the recommended no-PR standalone plugin layout and Community-by-default classification.
- Add `release_asset_repositories` support for monorepos that publish one or more `*.crosspoint-plugin.zip` assets from stable GitHub Releases.
- Validate release ZIPs safely, mirror declared runtime files under immutable per-plugin/version directories, and publish them through the normal Plugin Hub `base` plus `files` contract.
- Configure `readest/readest` as the first release-asset repository and process every matching CrossPoint plugin ZIP from its newest stable Release that contains one.

## 0.1.4

- Adopt the newer firmware `api.dir` plugin-directory API when available without requiring it on older firmware.
- Store Plugin Hub configuration as plugin-local `config.json` on newer firmware, while retaining `/.crosspoint/plugin-hub.json` as the compatibility fallback.
- Migrate legacy catalog settings by reading the old config when plugin-local config is absent, then saving future changes to the plugin directory without deleting the legacy file.
- Read Plugin Hub's own `manifest.json` from its actual runtime directory for self-version detection, with the legacy `/.crosspoint/plugins/pluginhub` lookup retained as a fallback.
- Add browser regression coverage for both the legacy API shape and the newer `api.dir` migration path.

## 0.1.3

- Add a release-promotion workflow that moves the `stable` branch to each published non-prerelease Plugin Hub release.
- Allow the stable-promotion workflow to run manually for a specific published stable tag or the latest stable Release.
- Make the bootstrap catalog versionless and point it at `stable`, so fresh installs receive the latest stable Plugin Hub without future catalog PRs.
- Rename the bootstrap catalog heading to `Plugin Hub` so users do not see the internal bootstrap label.
- Package every stable release as `pluginhub-X.Y.Z.zip`, expanding to `.crosspoint/plugins/pluginhub/` for direct SD-card installation without Plugin Store.
- Allow the release-package workflow to be run manually for a specific stable tag or the latest stable Release.
- Document direct SD-card installation, the firmware's in-place plugin loading behavior, and the catalog ID/title fallback rules.
- Correct the README to describe both the on-reader `device.json` catalog and browser-side `plugin.js` management UI.

## 0.1.2

- Standardize newly published Plugin Hub and discovered plugin versions on three-part `MAJOR.MINOR.PATCH` to match the CrossPoint firmware catalog contract.
- Tighten catalog-builder validation so two-part and four-part release versions are rejected for new catalog entries.
- Keep browser-side version comparison backward-compatible with legacy multi-part installed versions during migration.
- Point the bootstrap catalog at the immutable `v0.1.2` Plugin Hub release.
- Update the firmware note to reference CrossPoint PR #3824 for directional native version comparison.

## 0.1.1

- Add `whitelist.json` support for explicitly curated repositories and imported catalog entries.
- Import the existing CrossPoint Plugin Store entries except the legacy `send2ereader` entry.
- Resolve mutable GitHub Raw branch URLs from curated catalogs to immutable commit-SHA URLs.
- Prefer release-discovered plugins over curated catalog entries when the same plugin ID appears in both.
- Add the browser-side `plugin.js` management UI with install, update, reinstall, and remove controls.
- Show Plugin Hub's installed version in the WebUI and check the latest stable GitHub Release for an available self-update.
- Keep the generated Plugin Hub catalog as the built-in browser source while allowing users to add and remove extra custom, test, or private catalog URLs.
- Use directional two-to-four-part numeric version comparison in the browser UI so older catalog versions are not offered as downgrades.
- Add a browser integration test covering custom catalogs and directional update handling.
- Give generated catalogs a friendly `Plugin Hub` name instead of falling back to the raw host name.
- Document the complete self-service listing requirements, custom catalog format, troubleshooting checks, and version-tracking rules for release-discovered and curated plugins.

## 0.1.0

- Add the initial Plugin Hub CrossPoint plugin.
- Add GitHub discovery by `crosspoint-plugin` topic and compatible repository names.
- Generate catalog entries from stable GitHub Releases using immutable tag URLs.
- Support two-, three-, and four-part numeric versions, including an optional leading `v`.
- Validate release and manifest versions before publishing a catalog entry.
- Support explicit runtime file lists in `manifest.json`, with conventional CrossPoint files as the fallback.
- Add automated catalog refreshes and catalog-builder tests.
- Add a temporary bootstrap catalog for installing Plugin Hub through the existing CrossPoint Plugin Store before official catalog inclusion.
