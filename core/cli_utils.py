"""Shared helpers for validating external engine CLI binaries.

The per-engine data (candidate binaries, install hints, display names)
lives in :mod:`core.engine_registry` and is derived from it here, including
the legacy alias keys ("agy") the pre-registry tables used to carry — they
only ever produced alias-specific display names, and the alias spelling is
already accepted by :func:`require_engine_cli` via name normalization.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Iterable

from core.engine_registry import ALIASES, ENGINES

#: Alias kept for the historical import path; the registry is the source.
ENGINE_CLI_CANDIDATES: dict[str, tuple[str, ...]] = {
    spec.name: spec.cli_candidates for spec in ENGINES.values()
}

ENGINE_INSTALL_HINTS: dict[str, str] = {
    spec.name: spec.install_hint for spec in ENGINES.values()
}

ENGINE_DISPLAY_NAMES: dict[str, str] = {
    spec.name: spec.display_name for spec in ENGINES.values()
}


def _resolve_cli(candidates: Iterable[str], path: str | None) -> str | None:
    is_windows = sys.platform == "win32"
    for candidate in candidates:
        if not is_windows and candidate.lower().endswith((".cmd", ".bat", ".exe")):
            continue
        resolved = shutil.which(candidate, path=path)
        if resolved:
            return resolved
    return None


def require_engine_cli(engine_key: str, path: str | None = None) -> bool:
    """Print a friendly install hint when an external engine CLI is missing."""

    # Accept aliases ("agy") by normalizing to the canonical name first.
    canonical = ALIASES.get(engine_key.strip().lower(), engine_key)
    candidates = ENGINE_CLI_CANDIDATES.get(canonical, (canonical,))
    resolved = _resolve_cli(candidates, path)
    if resolved:
        return True

    display_name = ENGINE_DISPLAY_NAMES.get(canonical, canonical)
    install_hint = ENGINE_INSTALL_HINTS.get(canonical, "")

    print(f"Missing {display_name}.", file=sys.stderr)
    if install_hint:
        print("Install it first:", file=sys.stderr)
        print(f"  {install_hint}", file=sys.stderr)
    print("Then reopen your terminal and run:", file=sys.stderr)
    print(f"  ca {engine_key}", file=sys.stderr)
    return False
