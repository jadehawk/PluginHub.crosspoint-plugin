# CrossPoint Plugin Repository Standard

This document describes the repository layout Plugin Hub recommends for new CrossPoint plugins. It is a Plugin Hub publishing convention, not a firmware requirement.

## Recommended publishing path

Use one public GitHub repository per plugin, with the CrossPoint plugin files at the repository root.

A normal standards-compliant plugin does **not** need a Plugin Hub pull request. Add the `crosspoint-plugin` GitHub topic and publish a stable GitHub Release; Plugin Hub's scheduled discovery will evaluate it automatically.

A newly discovered plugin is published in **Community Plugins** unless maintainers explicitly classify that plugin ID and trusted source as Official in `catalog-policy.json`. Repository ownership does not determine Official status.

## Required repository shape

The repository root must contain:

```text
manifest.json
```

and at least one runnable CrossPoint entry point:

```text
device.json
plugin.js
```

Both entry points may be present.

Runtime files may also include `README.md` and other files explicitly declared by the manifest.

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
    "README.md"
  ]
}
```

Plugin IDs should use lowercase letters, digits, and hyphens. Versions must use `MAJOR.MINOR.PATCH`, for example `1.2.0`.

Every file required at runtime must either be one of Plugin Hub's conventional root files or be declared in `files`. Unsafe paths are rejected.

## GitHub Release requirements

1. Add the repository topic `crosspoint-plugin`.
2. Publish a non-draft, non-prerelease GitHub Release.
3. Use a Release tag matching the manifest version, optionally prefixed with `v`, such as `v1.2.0`.
4. The root `manifest.json` at that exact tag must declare the same version.
5. Publish a new version and Release for every runtime change that installed users should receive. Do not move or reuse an existing Release tag.

Plugin Hub publishes standalone repositories from the immutable Release tag, not from `main`.

## What happens after release

Plugin Hub's catalog workflow runs every three hours and can also be started manually. It discovers eligible repositories, validates their Release and runtime files, and publishes valid non-Official plugins in `community-catalog.json`.

No Plugin Hub pull request, whitelist entry, or issue is required for this normal path.

## When a Plugin Hub pull request is required

A pull request is required only for publishing paths that need explicit configuration, including:

- a monorepo that publishes one or more `*.crosspoint-plugin.zip` Release assets;
- a plugin that must temporarily be imported from another catalog;
- an exceptional standalone repository that cannot use automatic discovery;
- a maintainer-approved change to Official catalog policy.

These cases are configured in `whitelist.json` and/or `catalog-policy.json` as appropriate.

## Official versus Community

**Community** is the default classification for valid automatically discovered third-party plugins.

**Official** is explicit curation. An Official policy entry identifies both the plugin ID and its trusted source. If another repository claims the same Official ID, it cannot replace the trusted Official entry. Ambiguous duplicate Community IDs fail the catalog refresh instead of being resolved silently.

The generated `catalog.json` remains a compatibility union of Official and Community, but new Plugin Hub interfaces present the two catalogs separately.
