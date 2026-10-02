# Changelog

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
