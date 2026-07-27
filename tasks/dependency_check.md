# Dependency Check

Audit the project's declared dependencies for outdated, vulnerable, or unused packages.

## Objective

Produce a report of dependencies that should be upgraded, removed, or flagged for a security advisory — and upgrade the low-risk ones directly if asked to.

## Context

- Locate the dependency manifests actually in use (e.g. `pyproject.toml`/`uv.lock`, `package.json`/`package-lock.json` or `bun.lock`) — do not assume a single ecosystem.
- A major-version bump is a different risk tier than a patch release; treat them differently in the report.
- Respect any version pins that carry a comment explaining why — do not "fix" a deliberately pinned version without flagging it first.

## Instructions

1. List every direct dependency with its current pinned/resolved version and its latest available version.
2. Run the ecosystem's own audit tool where one exists (e.g. `pip-audit`, `npm audit`, `bun audit`) to surface known vulnerabilities; do not rely on version-number inspection alone for security issues.
3. Grep for actual usage of each dependency in source; call out any that appear unused.
4. Group findings by risk: security advisories first, then major-version bumps with breaking-change notes from the changelog, then routine patch/minor bumps.
5. If asked to apply fixes, only do so for patch/minor bumps with no reported breaking changes, then run the test suite; leave major bumps and removals for a human decision.

## Verification

Every flagged package is named with its current version, target version, and the specific reason (CVE id, "unused", "major bump"); if any upgrade was applied, the test suite passes afterward.
