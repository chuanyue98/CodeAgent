"""Shared constants used across CodeAgent's backend.

Single source of truth for values that were previously hand-duplicated
across many modules (see the 2026-07-28 engineering inspection) --
duplication meant adding or retiring an engine required remembering to
update every copy, with nothing catching a missed one.
"""

from __future__ import annotations

# The engine CLIs CodeAgent knows how to launch/manage. Used for
# request validation (reject an unknown `engine` field) and for iterating
# "every engine" (e.g. building the /api/engines list).
ENGINES = frozenset({"claude", "opencode", "codex", "codebuddy"})

# Directory under the system temp dir where engines drop the assembled
# prompt for a run. Shared so `ca doctor` probes the location engines
# really use -- it previously checked a project-root path that
# `write_temp_prompt` had long since stopped writing to.
TEMP_PROMPT_DIRNAME = "codeagent-prompts"
