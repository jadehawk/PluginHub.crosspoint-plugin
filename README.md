# Plugin Hub

Plugin Hub is a CrossPoint SD-card plugin that discovers, installs, and updates
plugins without requiring the CrossPoint firmware repository to host or maintain
the catalog.

Plugin Hub publishes two user-facing catalogs: **Official Plugins** for explicitly
curated CrossPoint ecosystem plugins and **Community Plugins** for valid third-party
plugins discovered from community developers. GitHub Actions does the heavier
discovery and classification work off-device.

For backward compatibility, `catalog.json` remains a generated union of both
catalogs. New Plugin Hub interfaces use a generated `catalog-lists.json` index so
Community can remain one catalog while small, or automatically become multiple
alphabetical shards when its compact serialized size approaches the firmware limit.
The compatibility union is not exposed as a third browsing choice.

> [!NOTE]
> **0.1.6 is intentionally staged on `main` but not yet released.** Production
> `stable` and the latest stable GitHub Release remain 0.1.5 until the supporting
> CrossPoint firmware changes for `browse.lists_url` and per-list notices are
> merged/released. This keeps existing plugin-enabled firmware on the compatible
> 0.1.5 release while 0.1.6 remains ready for the firmware rollout.

For maintainer details on whitelist/blacklist behavior, dynamic catalog generation,
firmware requirements, and the 2K/4K/6K torture test, see
[`PLUGIN_HUB_CATALOG_AND_FIRMWARE_REFERENCE.md`](PLUGIN_HUB_CATALOG_AND_FIRMWARE_REFERENCE.md).

## Get your plugin into Plugin Hub

> [!IMPORTANT]
> **The preferred automatic-discovery layout is one repository per plugin with the
> installable payload inside a direct child `<plugin-id>.crosspoint-plugin/` folder.**
> Add the `crosspoint-plugin` GitHub topic, publish a stable GitHub Release, and
> Plugin Hub will discover it automatically. No Plugin Hub PR is required.

For the definitive repository contract, see [`PLUGIN_REPOSITORY_STANDARD.md`](PLUGIN_REPOSITORY_STANDARD.md).

Using an AI coding agent to organize a plugin repository? Give it
[`PLUGIN_HUB_AGENT_GUIDE.md`](PLUGIN_HUB_AGENT_GUIDE.md).

Choose the path that matches how your plugin is published:

| Plugin layout | Catalog path | Pull request required? |
| --- | --- | --- |
| One plugin repository with `<plugin-id>.crosspoint-plugin/` payload directory | **Automatic discovery — RECOMMENDED** | **NO** |
| Plugin is published as one or more `*.crosspoint-plugin.zip` Release assets | **Secondary exception — release-asset monorepo** | **YES** |
| Plugin must be imported from another catalog | Curated/legacy catalog import | **YES** |
| Repository cannot reasonably use automatic discovery and needs an exception | Manual `repositories` entry | **YES — exception only** |

### Recommended: one repository per plugin — NO PR

This is the preferred way to publish a new CrossPoint plugin. Repository-root
development material can coexist cleanly with the plugin because Plugin Hub only
treats the direct child `<plugin-id>.crosspoint-plugin/` directory as the
installable payload.

A typical repository looks like this:

```text
my-plugin/
├── .github/
├── tests/
├── tools/
├── README.md                         # optional repository/development README
└── my-plugin.crosspoint-plugin/
    ├── manifest.json
    ├── device.json                   # at least device.json or plugin.js
    ├── plugin.js
    └── README.md                     # travels with the installed plugin
```

To publish through automatic discovery:

1. Host the plugin in a **public GitHub repository**.
2. Put the installable payload in exactly one direct child
   `<plugin-id>.crosspoint-plugin/` directory.
3. Make the directory stem exactly match `manifest.json -> name`.
4. Keep `manifest.json`, the plugin README, and at least one runnable entry point
   (`device.json` or `plugin.js`) inside that payload directory.
5. Keep development-only files outside the payload directory.
6. Add the GitHub repository topic **`crosspoint-plugin`**.
7. Use a three-part numeric version such as `1.2.0` in the payload manifest.
8. Publish a **non-draft, non-prerelease GitHub Release** whose tag matches that
   manifest version, for example `v1.2.0`.
9. Wait for the next Plugin Hub catalog refresh. It runs every three hours and can
   also be run manually by a maintainer.

Paths in `manifest.json -> files` are relative to the payload directory. The
folder name itself is not included in those file paths. Plugin Hub publishes the
catalog `base` directly at that payload directory.

**That is all. If the plugin follows this convention, no Plugin Hub PR is needed.**

Plugin Hub itself is the intentional root-layout exception because its firmware
bootstrap and production `stable` branch already depend on repository-root paths.
New plugins should not copy that exception.

### Monorepo / release-asset plugin — PR required

> [!IMPORTANT]
> This is a **secondary exception path**, not an equally preferred alternative to
> the one-plugin-per-repository standard. Keeping several CrossPoint plugins in one
> repository for convenience is not, by itself, a reason for Plugin Hub maintainers
> to add special configuration. Plugin authors are expected to isolate each plugin
> into its own standards-compliant repository whenever that is reasonably possible.
>
> Use this path only when the upstream project has a genuine monorepo constraint
> that makes separate plugin repositories impractical. Because this path adds a
> persistent source to Plugin Hub's configuration, it requires maintainer review and
> approval through a Plugin Hub pull request.

Use this when a project cannot reasonably use the preferred direct-child payload convention
and instead publishes one or more GitHub Release assets ending in
`.crosspoint-plugin.zip`.

1. Publish one or more `*.crosspoint-plugin.zip` assets on a stable GitHub Release.
2. Each ZIP must contain exactly one CrossPoint plugin root with `manifest.json`
   and `device.json` or `plugin.js`.
3. Open a **pull request to this Plugin Hub repository** adding only the GitHub
   `owner/repository` name to `whitelist.json -> release_asset_repositories`.
4. After that PR is merged, Plugin Hub automatically finds the newest stable
   Release containing matching assets, validates every matching ZIP, and publishes
   each valid plugin.

You do **not** configure a path, ZIP filename, asset pattern, or version in the
whitelist. Those are discovered from the Release assets themselves.

### Curated / legacy catalog import — PR required

Use this only when a plugin cannot yet use the recommended standalone layout or
the release-asset monorepo layout and must instead be imported from an existing
catalog.

Open a **pull request to this Plugin Hub repository** updating
`whitelist.json -> catalogs` with the upstream catalog URL and the specific plugin
ID or IDs to import. Plugin Hub never imports an entire external catalog implicitly.

Manual additions to `whitelist.json -> repositories` also require a pull request,
but they are intended as an exception rather than an alternate onboarding path. If
a standalone plugin can be reformatted to follow the recommended repository
convention and automatic-discovery rules, that should be preferred over adding a
manual allowlist entry.

## How it works

1. Plugin authors publish either a standalone CrossPoint plugin repository or a
   supported release-asset package.
2. Plugin Hub discovers standalone candidates on GitHub and also reads explicitly
   configured sources from `whitelist.json`.
3. `blacklist.json` removes repositories that must never be published, regardless
   of discovery, whitelist, release-asset, curated-catalog, or Official status.
4. The catalog builder validates versions and install files, then applies
   `catalog-policy.json`.
5. IDs explicitly listed in the policy are published in **Official Plugins** only
   when they resolve to their declared trusted source. All other valid discovered
   plugins are published in **Community Plugins**.
6. The builder writes compact machine JSON. Community stays in one file while it
   fits under the native response limit, then automatically splits into the minimum
   number of balanced contiguous alphabetical shards that fit.
7. The builder writes `catalog-lists.json`, which points at Official plus whatever
   Community shard layout currently exists and attaches the third-party warning to
   every Community entry.
8. Plugin Hub's `device.json` uses `browse.lists_url` to load that live index, so
   shard-count changes do not require a Plugin Hub release.
9. CrossPoint installs each selected bundle under
   `/.crosspoint/plugins/<plugin-id>/`.

Plugin Hub uses both CrossPoint plugin surfaces: `device.json` provides the
on-reader Official/Community chooser, while `plugin.js` provides the browser-side
management UI. Installation and updating still use CrossPoint's existing
declarative bundle installer.

## Detailed requirements for the recommended no-PR path

The checklist below expands on the automatic-discovery path above.

To make your plugin eligible for Plugin Hub:

1. Host the plugin in a **public GitHub repository**.
2. Add the GitHub repository topic **`crosspoint-plugin`**.
3. Create exactly one direct child `<plugin-id>.crosspoint-plugin/` payload directory.
4. Make the directory stem exactly match the plugin ID.
5. Keep `manifest.json`, the plugin README, and at least one runnable CrossPoint
   entry point (`device.json` or `plugin.js`) inside the payload directory.
6. Put every file that must be installed in the optional `files` array in
   `manifest.json`. If `files` is omitted, Plugin Hub only considers the
   conventional payload files `manifest.json`, `device.json`, `plugin.js`, and
   `README.md`.
7. Keep development-only files outside the payload directory.
8. Set a three-part numeric `MAJOR.MINOR.PATCH` version in `manifest.json`,
   for example `1.2.0`.
9. Publish a **non-draft, non-prerelease GitHub Release** with a matching version
   tag, for example `v1.2.0` for manifest version `1.2.0`.
10. Wait for the next Plugin Hub catalog refresh. The Action runs every three
    hours, and maintainers can also run it manually.

Repository names containing `crosspoint-plugin`, such as
`example.crosspoint-plugin` or `example-crosspoint-plugin`, are also searched
as a compatibility fallback. The **`crosspoint-plugin` topic is still the
recommended registration mechanism**. Plugin Hub deliberately does not globally
search for `.xp-plugin` because that name also matches unrelated ecosystems.

### Minimal manifest example

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

The recommended `name` format is lowercase letters, digits, and hyphens. For the
automatic folder-first path, the payload directory stem must exactly match this
plugin ID. Repository-name fallback exists only for compatibility and should not
be relied on by newly published plugins.

For automatically discovered repositories, the preferred display title comes from
`manifest.json -> title`. If that field is missing or not a string, Plugin Hub
falls back to the GitHub repository name. For curated catalog imports, a missing
or empty source title falls back to the plugin ID.

Development files such as tests, GitHub workflows, package metadata, and build
scripts belong outside the payload directory and are not installable through the
automatic folder-first path.

### If your plugin does not appear

Check these items first:

1. The repository is public.
2. The repository has the `crosspoint-plugin` topic, or its name contains the
   `crosspoint-plugin` phrase.
3. A stable GitHub Release exists. A tag by itself is not enough.
4. The Release is not marked draft or prerelease.
5. The Release tag is a supported numeric version.
6. Exactly one root-level `<plugin-id>.crosspoint-plugin/` payload directory exists
   at that exact Release tag.
7. That payload contains `manifest.json`, the plugin README, and `device.json` or
   `plugin.js`.
8. The payload directory stem matches the plugin ID and the manifest version matches
   the Release tag exactly after removing an optional leading `v`.
9. The install file list is safe and relative to the payload directory.

If any of those checks fail, the repository is skipped rather than publishing a
partially valid catalog entry.

## Version tracking

Version tracking is intentionally strict. Plugin Hub does **not** infer a newer
version from commit dates, changelog text, filenames, branch activity, or changed
file contents.

### Release-discovered plugins

For automatically discovered repositories and repositories explicitly listed
under `whitelist.json -> repositories`:

- The **latest stable GitHub Release** is the remote version source of truth.
- Supported published versions use exactly three numeric components: `MAJOR.MINOR.PATCH`,
  such as `1.2.3`.
- The GitHub Release tag may optionally begin with `v`.
- The payload `<plugin-id>.crosspoint-plugin/manifest.json` version at that tag
  must match the Release version.
- Plugin Hub publishes the normalized numeric version without the leading `v`.
- The generated catalog points to the exact Release tag and payload directory,
  never to mutable `main`.

**Every runtime change that should reach installed users must get a new version
and a new stable GitHub Release.** Do not change plugin files on `main` and
expect Plugin Hub to offer an update. Do not reuse or move an existing release
tag to different code.

If your plugin also exposes a version in `device.json` or another metadata file,
keep it synchronized with `manifest.json`. The installed plugin version used by
CrossPoint is expected to remain consistent with the published catalog version.

### Release-asset monorepos

Some projects ship several targets from one repository and cannot use the preferred
direct-child payload convention. **This release-asset path requires a pull request
to Plugin Hub.** The PR adds the GitHub `owner/repository` name, for example
`readest/readest`, under `whitelist.json -> release_asset_repositories`.

For these repositories, every catalog refresh scans stable GitHub Releases from
newest to oldest and selects the newest stable Release that contains one or more
assets ending in `.crosspoint-plugin.zip`. Every matching ZIP in that Release is
processed, so one monorepo Release can publish multiple CrossPoint plugins.

Each ZIP must contain exactly one CrossPoint plugin root, either directly at the
ZIP root or inside a directory. Its `manifest.json` must declare a three-part
`version`, and its declared runtime files must be safe and present. A valid
manifest `name` is used when present; otherwise a safe enclosing plugin directory
name, such as Readest's `readest/`, becomes the plugin ID. The plugin manifest
version is the version source of truth; it does not have to match the parent
monorepo Release tag.

Validated runtime files are mirrored into this repository under
`release-assets/<plugin-id>/<version>/`, then published through the same normal
`base` plus `files` catalog contract used by all other plugins. No CrossPoint
firmware or Plugin Hub installer change is required. A mirrored plugin version is
treated as immutable: if the same plugin/version later contains different bytes,
the refresh fails and the upstream plugin must publish a new manifest version.

If a newer stable monorepo Release has no CrossPoint asset yet, Plugin Hub keeps
using the newest earlier stable Release that does. If a configured repository has
no stable Release containing a matching asset, the refresh fails rather than
silently dropping a previously published plugin.

### Curated catalog imports

`whitelist.json` also supports importing selected plugin IDs from an existing
catalog. **This path requires a pull request to Plugin Hub.** It exists primarily
for current/legacy CrossPoint plugins that are not yet packaged as standalone
release-driven repositories or release-asset monorepos.

For these entries:

- `whitelist.json` contains the **catalog URL and allowed plugin IDs**, not a
  hardcoded version.
- On every refresh, Plugin Hub reads the current upstream catalog.
- The upstream catalog's **`version` field is the version source of truth**.
- Plugin Hub copies that version into the appropriate generated catalog.
- If the upstream `base` points to a GitHub Raw branch such as `main`, Plugin
  Hub resolves that branch to its current 40-character commit SHA so the files in
  the generated catalog are an immutable snapshot.

Classification is intentionally separate from source ingestion. `whitelist.json`
answers **where a candidate can come from**; `catalog-policy.json` answers **which
specific plugin IDs and sources are Official**; and `blacklist.json` answers **which
repositories must never be published at all**. Repository ownership alone never
makes a plugin Official, and the blacklist always wins over whitelist and Official
policy entries.

If an Official ID is also claimed by another source, the trusted source declared
in `catalog-policy.json` wins and the conflicting candidate is ignored. If two
Community candidates claim the same plugin ID, the catalog refresh fails instead
of silently selecting one.

**Changing files in an upstream branch without bumping the upstream catalog
version will not produce a usable version update for installed users.** The
snapshot SHA may change, but the version remains the same. Maintainers of curated
catalog entries must bump their catalog `version` whenever runtime plugin files
change.

The current whitelist imports selected entries from the existing CrossPoint
Plugin Store but intentionally excludes its legacy `send2ereader` entry.
`jadehawk/send2ereader.crosspoint-plugin` is release-discovered and is the
authoritative Community source for the `send2ereader` plugin ID.

## Curated whitelist

Automatic discovery should be used for new plugins whenever possible. A curated
entry is appropriate when a plugin cannot yet follow the standalone release
layout.

`whitelist.json` supports:

```json
{
  "repositories": [
    "owner/repository"
  ],
  "release_asset_repositories": [
    "readest/readest"
  ],
  "catalogs": [
    {
      "url": "https://example.com/catalog.json",
      "plugins": [
        "plugin-id"
      ]
    }
  ]
}
```

A repository listed in `repositories` still has to pass the same stable Release
and version checks as automatic discovery.

A repository listed in `release_asset_repositories` needs no per-plugin path,
asset filename, version, or pattern in the whitelist. Plugin Hub automatically
selects `*.crosspoint-plugin.zip` assets. The plugin version comes from each ZIP's
manifest; the plugin ID comes from a valid manifest `name` when present or falls
back to the safe enclosing plugin directory name.

A catalog listed in `catalogs` contributes **only** the plugin IDs explicitly
listed under `plugins`; Plugin Hub never imports every entry from a remote
catalog implicitly.

Any addition or removal under `repositories`, `release_asset_repositories`, or
`catalogs` changes this repository's `whitelist.json` and therefore requires a
Plugin Hub pull request. The recommended automatic-discovery path does not.

## Repository blacklist

`blacklist.json` is the repository-level deny list for generated catalogs:

```json
{
  "repositories": [
    "owner/repository"
  ]
}
```

Repository matching is case-insensitive. A blacklisted repository is omitted before
Official/Community classification, even if it is found automatically, appears in
`whitelist.json`, is configured as a release-asset repository, backs a curated
GitHub catalog/base URL, or is named as a trusted Official source in
`catalog-policy.json`.

Use the blacklist for repositories that Plugin Hub must not publish at all. Keep it
empty when no repositories need to be suppressed.

## Immutable sources

Release-discovered catalog entries point to the exact GitHub Release tag:

```text
https://raw.githubusercontent.com/OWNER/REPOSITORY/v0.1.0/
```

Curated entries imported from an existing catalog may begin with a mutable branch
URL, but GitHub Raw branch URLs are resolved to the branch's current 40-character
commit SHA before Plugin Hub publishes them. This keeps each generated catalog
entry tied to one immutable source snapshot.

Release-asset monorepo entries use generated versioned directories such as:

```text
https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/release-assets/readest/0.12.10/
```

The URL contains `main`, but each `<plugin-id>/<version>/` mirror is enforced as
immutable by the catalog builder. A refresh aborts instead of changing an
already-mirrored version in place.

## Catalog refresh

The `Refresh Plugin Catalog` workflow runs every three hours and can also be run
manually. It:

1. syncs to the current `main` branch;
2. runs the catalog builder and browser Plugin Hub test suites;
3. searches GitHub using the automatic discovery rules;
4. loads `whitelist.json`, including manually configured release-asset monorepos and
   catalog plugin IDs;
5. scans configured monorepo Releases for `*.crosspoint-plugin.zip`, validates
   every matching plugin ZIP, and mirrors runtime files into `release-assets/`;
6. validates release-driven entries and pins mutable GitHub Raw bases from curated
   catalogs to commit SHAs;
7. loads `catalog-policy.json` and resolves the explicitly trusted Official IDs;
8. rejects ambiguous Community plugin-ID collisions instead of choosing a winner;
9. rebuilds `official-catalog.json`, `community-catalog.json`, and compatibility
   union `catalog.json`;
10. commits all generated catalogs and any new release-asset mirror files only when
    staged contents changed.

The generated timestamp is preserved when the catalog contents are unchanged, so
scheduled runs do not create timestamp-only commits.

Separately, the `Promote Stable Plugin Hub Release` workflow moves the `stable`
branch to the exact commit behind each newly published non-prerelease Release.
It can also be run manually from GitHub Actions. A manually supplied stable tag is
validated before promotion; leaving the tag blank promotes the latest published
stable Release. That moving branch is used only as a bootstrap/install pointer.
Standalone release-discovered entries remain pinned to immutable Release tags,
curated GitHub Raw entries are pinned to commit SHAs, and release-asset entries use
versioned mirrors that the catalog builder enforces as immutable.

## Local validation

No third-party Python packages are required. Node.js is used for the browser-side
Plugin Hub test.

```powershell
python -m unittest discover -s tests -v
node --test tests/test_plugin_js.mjs
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
plugin.js
README.md
```

### Direct SD-card install

Each stable GitHub Release includes a `pluginhub-X.Y.Z.zip` asset for users who
do not want to install Plugin Store first.

Extract the ZIP at the root of the SD card. It expands to:

```text
.crosspoint/
└── plugins/
    └── pluginhub/
        ├── manifest.json
        ├── device.json
        ├── plugin.js
        └── README.md
```

CrossPoint scans `/.crosspoint/plugins` directly, so the plugin runs from that
location; the firmware does not copy it to another plugin directory.

### Install through Plugin Store

Until Plugin Hub is included in the default CrossPoint Plugin Store catalog, it
can also be bootstrapped through the existing Plugin Store by temporarily adding
this Store URL:

```text
https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/bootstrap-catalog.json
```

The bootstrap catalog points to the `stable` branch, which advances only when a
non-prerelease GitHub Release is published. Fresh installs therefore receive the
latest stable Plugin Hub without tracking unreleased `main` commits. After Plugin
Hub is installed, the temporary bootstrap Store can be removed.

### On the reader

Open:

```text
Settings → System → Plugins → Plugin Hub
```

The reader uses the firmware's existing `browse.lists` support and first presents
two choices:

```text
Official Plugins
Community Plugins
```

Selecting either entry opens the normal plugin list for that catalog. Back from a
plugin list returns to the Official/Community chooser. No firmware-specific Plugin
Hub code is required for this split.

### From the device web UI

Plugin Hub also mounts a browser-side management card under **Settings** through
`plugin.js`. The card shows the installed Plugin Hub version from its own
`manifest.json` and checks the latest stable GitHub Release. It provides the same
plugin-management actions as before:

- install an available plugin;
- update when the catalog version is newer than the installed version;
- reinstall the same version;
- remove an installed plugin;
- show installed/catalog versions and update counts.

The browser card shows **Official Plugins** and **Community Plugins** as two
non-removable built-in browse choices. Official is selected when Plugin Hub opens,
and only the selected catalog is loaded at a time. The compatibility `catalog.json`
feed is not shown as another choice.

#### Add custom, test, or private catalogs

Expand **Custom catalogs** to add another catalog URL. Custom catalogs remain
separate from the two built-ins and can be selected with **Browse**.

On firmware that provides the newer plugin-directory API, Plugin Hub stores its
configuration inside its actual plugin directory as `config.json`. This keeps the
configuration with the plugin regardless of whether it is loaded from
`/.crosspoint/plugins`, `/plugins`, or `/.plugins`.

On older firmware that does not provide `api.dir`, Plugin Hub remains compatible
with the legacy config path:

```text
/.crosspoint/plugin-hub.json
```

When a newer firmware first exposes `api.dir`, Plugin Hub checks the plugin-local
`config.json` first, then falls back to the legacy file. If the legacy file is
used, the next save writes the same settings to the plugin-local config without
deleting the legacy file, preserving downgrade compatibility.

Plugin Hub also uses `api.dir` when available to read its own `manifest.json`
for self-version detection, with the legacy `/.crosspoint/plugins/pluginhub`
lookup retained as a fallback.

A custom catalog becomes another secondary browser choice; it is not merged into
Official or Community. A custom catalog can be hosted on GitHub Raw, a LAN server,
a private/test web server, or another HTTP(S) endpoint that the device can fetch.

A minimal custom catalog is:

```json
{
  "name": "My Private Plugins",
  "plugins": [
    {
      "name": "my-test-plugin",
      "title": "My Test Plugin",
      "description": "Private test build.",
      "author": "Me",
      "version": "0.0.1",
      "base": "https://example.test/my-test-plugin/",
      "files": [
        "manifest.json",
        "plugin.js"
      ]
    }
  ]
}
```

The optional top-level `name` is used as the catalog heading. If it is omitted,
Plugin Hub displays the catalog host name instead.

The browser UI does not currently manage arbitrary authentication headers or
credentials for private catalogs. If authentication is required, use a URL the
device can fetch directly, such as a signed URL or a reachable authenticated
endpoint that does not require interactive browser login.

Custom catalogs are currently a **browser-side Plugin Hub feature**. The on-reader
Plugin Hub screen exposes only the built-in Official and Community catalogs defined
in `device.json`.

## Trust model

**Official** is an explicit curation classification, not an inference from the
repository owner or where a plugin is hosted. Each Official plugin ID is tied to a
trusted source in `catalog-policy.json`.

**Community** contains valid plugins from third-party developers that are not
explicitly classified Official. Automatic discovery and schema validation do not
constitute a security review or endorsement; users should treat third-party
plugins as software from their respective publishers.

## Current firmware note

Plugin Hub does not require a CrossPoint firmware change to function. CrossPoint
PR #3824 adds directional native catalog version comparison and defines plugin
versions as three-part `MAJOR.MINOR.PATCH`. Plugin Hub now publishes only that
three-part format. Older firmware may still label any installed/catalog version
mismatch as an update until that firmware fix is present.
