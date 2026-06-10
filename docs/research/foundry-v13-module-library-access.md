# Foundry v13 Module Library Access Research

Date: 2026-06-09

## Question

Can `foundry-admin-cli` access the official Foundry module/system package library by package ID, instead of requiring operators to paste manifest URLs?

## Sources

- Official package management docs: <https://foundryvtt.com/article/package-management>
- Official package release API docs: <https://foundryvtt.com/article/package-release-api>
- Local Foundry v13.351 source:
  - `dist/server/views/setup.mjs`
  - `dist/packages/views.mjs`
  - `dist/packages/package.mjs`
  - `dist/packages/module.mjs`
  - `dist/packages/system.mjs`
  - `common/packages/base-package.mjs`
  - `common/packages/base-module.mjs`

## Findings

Foundry already exposes the official package library through setup/admin actions. The setup POST action switch includes:

- `getPackages`
- `getPackageFromRemoteManifest`
- `checkPackage`
- `installPackage`

These actions are available through the same `/setup` admin route that `foundry-admin-cli` already uses for package install, backup, world lifecycle, and admin-session checks.

The route has the same setup-mode boundary as other setup actions:

- no active world
- authenticated setup/admin session

If a world is active, setup actions are blocked unless the request is one of the narrow in-world exceptions handled by Foundry source.

## Official repository endpoint used by Foundry

Server package code calls the Foundry website package repository endpoint:

```text
POST https://foundryvtt.com/_api/packages/get
```

with JSON shaped from source as:

```json
{
  "type": "module",
  "version": "13.351",
  "license": "<Foundry license data object>"
}
```

Headers include:

```text
Content-Type: application/json
Authorization: <Foundry license authorization header>
```

The direct website endpoint is therefore license-aware and should not be called by the CLI with hand-rolled credential handling unless there is a strong reason. Prefer Foundry's setup action, which already has access to the local license configuration and redaction boundaries.

## Setup action behavior

`packages.getPackages({type})`:

1. Maps `type` through `PACKAGE_TYPE_MAPPING`.
2. Calls `PackageClass.getRepositoryPackages()`.
3. Returns:

```js
{
  packages: Array.from(repositoryPackages.values()).map(pkg => pkg.vend()),
  owned: ownedPackageIds
}
```

Supported useful `type` values are at least:

- `module`
- `system`

World packages are local user data and are not expected to be discovered from the public package library.

`PackageClass.getRepositoryPackages()`:

- caches repository data for about 5 minutes
- sends the current Foundry release version to the website
- includes local license data/authorization
- returns a package map and owned/protected package IDs
- transforms website repository records via `fromRepositoryData()`

`fromRepositoryData()` maps website records into normal Foundry package-like objects, including:

- `id` from website `name`
- `title`
- `version`
- `description`
- `authors`
- `url`
- `manifest`
- `compatibility.minimum`
- `compatibility.verified`
- `compatibility.maximum`
- `relationships.systems`
- `tags`
- `exclusive`
- `protected`
- `owned`

The returned `vend()` data also includes availability-related fields such as `availability`, `locked`, `exclusive`, `owned`, `tags`, and `hasStorage` where applicable.

## Install-by-ID strategy

Foundry's actual `installPackage` setup action still requires a manifest URL. The missing CLI feature is not "install ID directly" in Foundry core; it is a pre-resolution step:

1. Authenticate setup admin.
2. Ensure setup mode/no active world.
3. Call `setup_action("getPackages", {"type": "module"})` or `type=system`.
4. Filter/search returned library rows locally.
5. Select exact package ID.
6. Read its `manifest` URL from the returned package data.
7. Pass that manifest into existing `module install <manifest-url>` / `system install <manifest-url>` flow.

This preserves the current safe manifest URL validation and setup `installPackage` behavior while adding package-ID convenience.

## Recommended CLI surface

Keep existing manifest-URL install commands. Add explicit package-library commands:

```bash
fvtt --version v13 module library search <query> --json
fvtt --version v13 module library show <package-id> --json
fvtt --version v13 module install-id <package-id> --json
fvtt --version v13 system library search <query> --json
fvtt --version v13 system library show <package-id> --json
fvtt --version v13 system install-id <package-id> --json
```

Alternative shorter names are acceptable, but avoid plural namespace drift. Current CLI namespaces are singular: `module`, `system`, `world`, `game`, `backup`.

## Filtering recommendations

For `library search`, support local filters over the returned repository rows:

- query over `id`, `title`, `description`, author names, and tags
- `--tag <tag>`
- `--system <system-id>` for modules with system relationships
- `--compatible-only` using Foundry-provided `availability` if trustworthy from vend data
- `--owned-only` / `--free-only` using `owned`, `protected`, and `exclusive`
- `--limit N`

Do not invent compatibility semantics when Foundry already calculates `availability`. If more precise compatibility is needed, call `checkPackage` on the selected manifest and return Foundry's result.

## Safety and privacy

- Do not echo license data, authorization headers, cookies, raw setup responses, or package auth results.
- Treat protected/owned package metadata as potentially user/license-specific.
- Keep direct calls to `https://foundryvtt.com/_api/packages/get` out of the first implementation. Use Foundry's setup action instead.
- Keep setup-mode failure structured and clear: active world, unauthenticated admin, or package repository unavailable.
- Continue rejecting non-http(s) manifest URLs before installation.

## Recommended implementation slice

1. Add a shared package-library helper:
   - `list_library_packages(client, package_type)` calls `getPackages`.
   - normalize to safe fields: `id`, `title`, `version`, `manifest`, `compatibility`, `relationships`, `tags`, `owned`, `protected`, `exclusive`, `availability`.
2. Add read-only commands:
   - `module library search`
   - `module library show`
   - `system library search`
   - `system library show`
3. Add install-by-ID commands after read-only commands are tested:
   - resolve exact package ID to manifest URL
   - call existing install helper
   - require `--force` only for downgrade/sidegrade behavior if Foundry check says it is unsafe
4. Add tests:
   - setup action payload shape
   - search filtering
   - package ID exact-match ambiguity/missing handling
   - no license/cookie/raw auth leakage in JSON/human output
   - active-world/admin-session error shape

## Bottom line

The admin CLI can access the official Foundry module/system library without scraping the website and without asking users for credentials. The right primitive is Foundry's existing setup action `getPackages`, not a new direct API client. Install-by-ID should be implemented as package-library lookup followed by the existing manifest-based install path.
