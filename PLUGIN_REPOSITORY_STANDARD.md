# CrossPoint Plugin Repository Standard

This document defines the repository layout Plugin Hub expects for automatically discovered CrossPoint plugins. It is a Plugin Hub publishing convention, not a firmware requirement.

## Preferred publishing path

Use **one public GitHub repository per plugin**.

The installable CrossPoint payload must live inside one direct child directory named:

```text
<plugin-id>.crosspoint-plugin/
```

This keeps development files, tests, screenshots, build tooling, CI configuration, documentation sources, and other repository-only content separate from the files that Plugin Hub installs on a reader.

A normal standards-compliant plugin does **not** need a Plugin Hub pull request. Add the `crosspoint-plugin` GitHub topic and publish a stable GitHub Release; Plugin Hub's scheduled discovery will evaluate it automatically.

A newly discovered plugin is published in **Community Plugins** unless maintainers explicitly classify that plugin ID and trusted source as Official in `catalog-policy.json`. Repository ownership does not determine Official status.

## Required repository shape

A typical repository should look like this:

```text
example-plugin/
├── .github/
├── docs/
├── tests/
├── tools/
├── README.md                  # optional repository/development documentation
└── example-plugin.crosspoint-plugin/
    ├── manifest.json
    ├── device.json            # at least device.json or plugin.js is required
    ├── plugin.js
    ├── README.md              # installable plugin README
    └── assets/
        └── icon.png
```

Plugin Hub only treats the direct child `*.crosspoint-plugin/` directory as the installable payload. Repository-root development files are ignored.

The payload directory must contain `manifest.json` and at least one runnable CrossPoint entry point:

```text
device.json
plugin.js
```

Both entry points may be present.

The plugin README should travel with the plugin and therefore belongs inside the payload directory. Additional runtime files and nested runtime directories are allowed when they are declared in `manifest.json -> files`.

Automatic discovery currently expects exactly one root-level `*.crosspoint-plugin/` payload directory per repository. The preferred standard remains one repository per plugin.

## Payload directory naming

The directory stem must exactly match the plugin ID declared by `manifest.json`:

```text
example-plugin.crosspoint-plugin/
```

```json
{
  "name": "example-plugin"
}
```

Plugin IDs use lowercase letters, digits, and hyphens.

## Manifest requirements

`manifest.json` must contain a safe plugin ID and a three-part numeric version. A typical manifest is:

```json
{
  "name": "example-plugin",
  "title": "Example Plugin",
  "description": "What the plugin does.",
  "author": "Author Name",
  "version": "1.2.0",
  "files": [
    "manifest.json",
    "device.json",
    "plugin.js",
    "README.md",
    "assets/icon.png"
  ]
}
```

Versions must use `MAJOR.MINOR.PATCH`, for example `1.2.0`.

Paths in `files` are relative to the payload directory, not the repository root. Do not prefix entries with `<plugin-id>.crosspoint-plugin/`.

Every file required by the installed plugin should be declared in `files`. If `files` is omitted, Plugin Hub falls back to the conventional payload files `manifest.json`, `device.json`, `plugin.js`, and `README.md` when present. Unsafe paths are rejected.

Development-only files outside the payload directory are never installed.

## GitHub Release requirements

1. Add the repository topic `crosspoint-plugin`.
2. Publish a non-draft, non-prerelease GitHub Release.
3. Use a Release tag matching the manifest version, optionally prefixed with `v`, such as `v1.2.0`.
4. At that exact tag, `<plugin-id>.crosspoint-plugin/manifest.json` must declare the same version.
5. Publish a new version and Release for every runtime change that installed users should receive. Do not move or reuse an existing Release tag.

Plugin Hub publishes automatically discovered repositories from the immutable Release tag, not from `main`.

The generated catalog `base` points directly at the payload directory. Catalog `files` entries remain relative to that payload root.

## What happens after release

Plugin Hub's catalog workflow runs every three hours and can also be started manually. It discovers eligible repositories, validates the Release and payload directory, and publishes valid non-Official plugins in the Community catalog.

No Plugin Hub pull request, whitelist entry, or issue is required for this normal path.

## Plugin Hub repository exception

`jadehawk/PluginHub.crosspoint-plugin` intentionally remains a root-layout exception.

Plugin Hub's own firmware/bootstrap integration and generated catalogs already depend on repository-root paths and on the production `stable` branch. Its payload layout is therefore not being reorganized as part of this standard reset.

This exception is specific to Plugin Hub and should not be copied by new plugins.

## When a Plugin Hub pull request is required

A pull request is required only for publishing paths that need explicit configuration, including:

- a monorepo that publishes one or more `*.crosspoint-plugin.zip` Release assets;
- a plugin that must temporarily be imported from another catalog;
- an exceptional repository that cannot use automatic discovery;
- a maintainer-approved change to Official catalog policy.

These cases are configured in `whitelist.json` and/or `catalog-policy.json` as appropriate.

## Official versus Community

**Community** is the default classification for valid automatically discovered third-party plugins.

**Official** is explicit curation. An Official policy entry identifies both the plugin ID and its trusted source. If another repository claims the same Official ID, it cannot replace the trusted Official entry. Ambiguous duplicate Community IDs fail the catalog refresh instead of being resolved silently.

The generated `catalog.json` remains a compatibility union of Official and Community, but new Plugin Hub interfaces present the two catalogs separately.
