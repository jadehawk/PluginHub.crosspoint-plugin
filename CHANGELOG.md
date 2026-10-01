# Changelog

## Unreleased

- Add `whitelist.json` support for explicitly curated repositories and imported catalog entries.
- Import the existing CrossPoint Plugin Store entries except the legacy `send2ereader` entry.
- Resolve mutable GitHub Raw branch URLs from curated catalogs to immutable commit-SHA URLs.
- Prefer release-discovered plugins over curated catalog entries when the same plugin ID appears in both.

## 0.1.0

- Add the initial Plugin Hub CrossPoint plugin.
- Add GitHub discovery by `crosspoint-plugin` topic and compatible repository names.
- Generate catalog entries from stable GitHub Releases using immutable tag URLs.
- Support two-, three-, and four-part numeric versions, including an optional leading `v`.
- Validate release and manifest versions before publishing a catalog entry.
- Support explicit runtime file lists in `manifest.json`, with conventional CrossPoint files as the fallback.
- Add automated catalog refreshes and catalog-builder tests.
- Add a temporary bootstrap catalog for installing Plugin Hub through the existing CrossPoint Plugin Store before official catalog inclusion.
