"""Shared constants used across CodeAgent's backend.

Single source of truth for values that were previously hand-duplicated
across many modules (see the 2026-07-28 engineering inspection) --
duplication meant adding or retiring an engine required remembering to
update every copy, with nothing catching a missed one.

Engine identity itself lives in :mod:`core.engine_registry` (AUDIT-002);
this module re-exports it so the historical import path keeps working.
"""

from __future__ import annotations

from core.engine_registry import ALIASES as _REGISTRY_ALIASES
from core.engine_registry import engine_names
from core.engine_registry import normalize_engine_name as _registry_normalize

# The engine CLIs CodeAgent knows how to launch/manage. Used for
# request validation (reject an unknown `engine` field) and for iterating
# "every engine" (e.g. building the /api/engines list). Derived from the
# declarative EngineSpec registry, so adding an engine is a one-edit change.
ENGINES = engine_names()

# Engines that support headless/non-interactive execution mode.
# Currently every launchable engine is headless-capable; the distinction
# is kept as a name because several call sites ask the question
# specifically. If an engine ever ships without a non-interactive mode,
# carve it out here rather than at every call site.
HEADLESS_ENGINES = ENGINES

# Engines that support MCP server configuration and synchronization.
# Currently all of them; same carve-out note as HEADLESS_ENGINES.
MCP_ENGINES = ENGINES

# Directory under the system temp dir where engines drop the assembled
# prompt for a run. Shared so `ca doctor` probes the location engines
# really use -- it previously checked a project-root path that
# `write_temp_prompt` had long since stopped writing to.
TEMP_PROMPT_DIRNAME = "codeagent-prompts"

# Canonical engine aliases (derived from the registry, plus the legacy
# "gemini" spelling from the retired Gemini engine -- kept so old configs
# and session records still resolve instead of erroring).
ENGINE_ALIASES: dict[str, str] = dict(_REGISTRY_ALIASES)


def normalize_engine_name(name: str) -> str:
    """Normalizes an engine identifier or alias to its canonical name."""
    return _registry_normalize(name)
