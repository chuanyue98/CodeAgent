"""Shared helpers for validating external engine CLI binaries."""

from __future__ import annotations

import shutil
import sys
from typing import Iterable

ENGINE_CLI_CANDIDATES: dict[str, tuple[str, ...]] = {
    "claude": ("claude", "claude.cmd"),
    "gemini": ("gemini", "gemini.cmd"),
    "opencode": ("opencode", "opencode.cmd"),
    "codex": ("codex", "codex.cmd"),
}

ENGINE_INSTALL_HINTS: dict[str, str] = {
    "claude": "npm install -g @anthropic-ai/claude-code",
    "gemini": "npm install -g @google/gemini-cli",
    "opencode": "npm install -g opencode-ai",
    "codex": "npm install -g @openai/codex",
}

ENGINE_DISPLAY_NAMES: dict[str, str] = {
    "claude": "Claude Code",
    "gemini": "Gemini CLI",
    "opencode": "OpenCode",
    "codex": "Codex",
}


def _resolve_cli(candidates: Iterable[str], path: str | None) -> str | None:
    is_windows = sys.platform == "win32"
    for candidate in candidates:
        if not is_windows and (candidate.endswith(".cmd") or candidate.endswith(".bat") or candidate.endswith(".exe")):
            continue
        resolved = shutil.which(candidate, path=path)
        if resolved:
            return resolved
    return None


def require_engine_cli(engine_key: str, path: str | None = None) -> bool:
    """Print a friendly install hint when an external engine CLI is missing."""

    candidates = ENGINE_CLI_CANDIDATES.get(engine_key, (engine_key,))
    resolved = _resolve_cli(candidates, path)
    if resolved:
        return True

    display_name = ENGINE_DISPLAY_NAMES.get(engine_key, engine_key)
    install_hint = ENGINE_INSTALL_HINTS.get(engine_key, "")

    print(f"Missing {display_name}.", file=sys.stderr)
    if install_hint:
        print("Install it first:", file=sys.stderr)
        print(f"  {install_hint}", file=sys.stderr)
    print("Then reopen your terminal and run:", file=sys.stderr)
    print(f"  ca {engine_key}", file=sys.stderr)
    return False
