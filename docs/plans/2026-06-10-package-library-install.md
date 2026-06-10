# Package Library Install Implementation Plan

> **For Hermes:** Implement directly with strict TDD.

**Goal:** Add system/module package-library lookup commands and install-by-package-id support.

**Architecture:** Add shared helpers in `packages.py` that call authenticated setup action `getPackages`, normalize Foundry package metadata, resolve exact package IDs to manifest URLs, and reuse existing `installPackage` manifest install. Wire `system library search/show`, `module library search/show`, and allow `system install <id>` / `module install <id>` to resolve IDs when the argument is not an HTTP(S) URL.

**Tech Stack:** Python argparse CLI, pytest, Foundry setup/admin client abstraction.

## Tasks

1. Add failing unit tests in `tests/test_packages.py` for library list/filter, exact show, missing/ambiguous ID failure, and install-by-ID resolving before `installPackage`.
2. Add failing CLI tests in `tests/test_systems_cli.py` and `tests/test_modules_cli.py` for `library search`, `library show`, and install-by-ID wiring.
3. Implement shared package library helpers in `src/foundry_admin_cli/packages.py`.
4. Wire argparse and dispatch in `src/foundry_admin_cli/cli.py`.
5. Run focused tests, then full test suite and `git diff --check`.
6. Run independent diff review, fix any blockers, commit and push.
