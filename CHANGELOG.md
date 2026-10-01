# Changelog

## 0.1.1

- Add `whitelist.json` support for explicitly curated repositories and imported catalog entries.
- Import the existing CrossPoint Plugin Store entries except the legacy `send2ereader` entry.
- Resolve mutable GitHub Raw branch URLs from curated catalogs to immutable commit-SHA URLs.
- Prefer release-discovered plugins over curated catalog entries when the same plugin ID appears in both.
- Add the browser-side `plugin.js` management UI with install, update, reinstall, and remove controls.
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
