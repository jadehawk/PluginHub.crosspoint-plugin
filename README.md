# Plugin Hub

Plugin Hub is a CrossPoint SD-card plugin that discovers, installs, and updates
community plugins without requiring the CrossPoint firmware repository to host or
maintain the community catalog.

The reader only consumes this repository's generated `catalog.json`. GitHub
Actions does the heavier discovery work off-device.

## How it works

1. Plugin authors publish a normal CrossPoint plugin repository.
2. Plugin Hub discovers candidate repositories on GitHub.
3. The catalog builder validates the latest stable GitHub Release.
4. `catalog.json` is generated with immutable release-tag URLs.
5. Plugin Hub's `device.json` presents that catalog using CrossPoint's built-in
   plugin catalog UI.
6. CrossPoint installs each selected bundle under
   `/.crosspoint/plugins/<plugin-id>/`.

Plugin Hub itself contains no on-device JavaScript. Installation and updating are
handled by CrossPoint's existing declarative `device.json` bundle installer.

## Discovery

The catalog builder searches GitHub for:

- repositories with the `crosspoint-plugin` topic;
- repositories whose name contains the distinctive `crosspoint-plugin` phrase.

The `crosspoint-plugin` topic is the registration mechanism for normal
`.xp-plugin` repositories. Names such as `example.crosspoint-plugin` and
`example-crosspoint-plugin` are retained as compatibility fallbacks. Plugin Hub
deliberately does not search globally for `.xp-plugin` because that term also
matches large numbers of unrelated X-Plane, Xposed, and other repositories.

Plugin Hub excludes its own repository from the generated catalog.

## Plugin requirements

A discovered repository must have a stable GitHub Release whose tag is a numeric
version in one of these forms:

- `v1.2`
- `v1.2.3`
- `v1.2.3.4`

The leading `v` is optional.

At that release tag, the repository must contain a root `manifest.json`. Its
`version` must match the release tag after removing the optional leading `v`.

A typical manifest is:

```json
{
  "name": "example",
  "title": "Example Plugin",
  "description": "What the plugin does.",
  "author": "Author Name",
  "version": "0.1.0",
  "files": [
    "manifest.json",
    "device.json",
    "plugin.js",
    "README.md"
  ]
}
```

`name` should use lowercase letters, digits, and hyphens. If it is omitted,
Plugin Hub derives the plugin ID from the repository name by stripping
`.xp-plugin` or `.crosspoint-plugin`.

### Runtime files

The optional `files` array is the authoritative install list for Plugin Hub.
Use it when the plugin needs nested assets or any runtime files beyond the normal
CrossPoint files.

When `files` is omitted, Plugin Hub automatically includes whichever of these
root files exist:

```text
manifest.json
device.json
plugin.js
README.md
```

A valid plugin must include `manifest.json` plus at least one of
`device.json` or `plugin.js`.

Development files such as tests, GitHub workflows, package metadata, and build
scripts are not installed unless a plugin explicitly lists them in `files`.

## Immutable releases

Catalog entries point to the exact GitHub release tag:

```text
https://raw.githubusercontent.com/OWNER/REPOSITORY/v0.1.0/
```

They never point at a mutable `main` branch. This keeps the catalog version and
the files installed by CrossPoint tied to the same release.

## Catalog refresh

The `Refresh Plugin Catalog` workflow runs every three hours and can also be run
manually. It:

1. runs the catalog builder test suite;
2. searches GitHub using the discovery rules above;
3. validates each latest stable release;
4. rebuilds `catalog.json`;
5. commits the catalog only when its plugin contents changed.

The generated timestamp is preserved when the catalog contents are unchanged, so
scheduled runs do not create timestamp-only commits.

## Local validation

No third-party Python packages are required.

```powershell
python -m unittest discover -s tests -v
python tools/build_catalog.py
```

Unauthenticated GitHub API requests are rate-limited. Set `GITHUB_TOKEN` or
`GH_TOKEN` for local catalog builds when needed. GitHub Actions automatically
uses the repository token.

## CrossPoint installation

Plugin Hub is a normal CrossPoint plugin. Its runtime files are:

```text
manifest.json
device.json
README.md
```

Until Plugin Hub is included in the default CrossPoint Plugin Store catalog, it
can be bootstrapped through the existing Plugin Store by temporarily adding this
Store URL:

```text
https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/bootstrap-catalog.json
```

That bootstrap catalog contains only Plugin Hub and installs the immutable
`v0.1.0` release. After Plugin Hub is installed, the temporary bootstrap Store
can be removed.

Once Plugin Hub itself is installed, open it from:

```text
Settings → System → Plugins → Plugin Hub
```

The catalog is then fetched directly from this repository and displayed by the
firmware's standard plugin catalog screen.

## Trust model

Plugin Hub discovers community repositories automatically. Discovery and schema
validation do not constitute a security review or endorsement of a plugin.
Users should treat third-party plugins as software from their respective
publishers.

## Current firmware note

Plugin Hub does not require a CrossPoint firmware change to function. Current
firmware may label any installed/catalog version mismatch as an update, including
the uncommon case where a manually installed plugin is newer than the generated
catalog. Correct directional version comparison can be addressed separately in
CrossPoint without blocking Plugin Hub development or use.
