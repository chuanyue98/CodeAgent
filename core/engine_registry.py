"""Single declarative registry of the engines CodeAgent can launch.

Before this module, "which engines exist" was hand-copied in six places:
``core/constants.ENGINES``, the ``engine_script_map`` in ``core.cli.main``,
the ``ENGINE_BINARIES``/``ENGINE_INSTALL_HINTS`` tables in ``core/doctor``,
the candidates/hints/display-name dicts in ``core.cli_utils``, the
``_CHAT_SESSION_ID_FIELDS`` map and the ``_build_engine`` if-chain in
``core.services.runner_service``, and the ``click.Choice`` in
``core.cli.commands.tasks``. Adding an engine meant remembering all of them;
missing one produced no warning (doctor's own comment admitted an engine
absent there "silently says nothing about" itself).

Every derived list/map in this project now reads from :data:`ENGINES` below.
Adding a new engine means:

1. Create the adapter modules themselves (real per-engine code, cannot be
   derived): ``engines/start_<name>.py``, a session-history parser and
   writer, an analytics collector, and MCP config-path handling.
2. Add one :class:`EngineSpec` entry here.

Everything else — CLI dispatch, doctor checks, install hints, click choices,
chat-session-id extraction — updates automatically.

Deliberately *not* centralized here (each is genuine per-engine code, not a
copy of a list): session-history parser/writer registries, analytics
collectors, per-engine MCP config paths, and the Web-side Agent Gateway
adapter factories (a separate, experimental subsystem with its own provider
set — see ``core/web/server.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EngineSpec:
    """Everything CodeAgent needs to know about one engine, in one place."""

    #: Canonical name — the value used in config.json, the CLI, and the API.
    name: str
    #: Human-readable name for user-facing output.
    display_name: str
    #: Launch script filename inside ``engines/``.
    launch_script: str
    #: Binary names probed on PATH, in order (Windows-only suffixes allowed
    #: and skipped on POSIX).
    cli_candidates: tuple[str, ...]
    #: One-line install hint shown by doctor / require_engine_cli.
    install_hint: str
    #: Dotted path of the launcher class used by TaskRunner's
    #: ``_build_engine`` (imported lazily to avoid a core→engines→core
    #: import cycle).
    adapter: str
    #: JSON(L) field names a chat turn's log may carry the engine-reported
    #: session id under — codex calls it thread_id, the rest vary.
    session_id_fields: tuple[str, ...] = ()
    #: Alternate spellings accepted on the CLI and in config
    #: (``ca agy``, ``"engine": "agy"``). The canonical name itself needs
    #: no entry here.
    aliases: tuple[str, ...] = field(default_factory=tuple)


#: Legacy alias from the retired Gemini engine (removed in commit 680b4d4,
#: superseded by Antigravity). Kept here so old configs and session records
#: still resolve to antigravity instead of erroring. Not an EngineSpec.aliases
#: entry because it must not appear in CLI help or the script map as a
#: launch spelling of a live engine — it only normalizes.
_LEGACY_ALIASES: dict[str, str] = {
    "gemini": "antigravity",
}


ENGINES: dict[str, EngineSpec] = {
    spec.name: spec
    for spec in (
        EngineSpec(
            name="claude",
            display_name="Claude Code",
            launch_script="start_claude_code.py",
            cli_candidates=("claude", "claude.cmd"),
            install_hint="npm install -g @anthropic-ai/claude-code",
            adapter="engines.start_claude_code:ClaudeEngine",
            session_id_fields=("session_id",),
        ),
        EngineSpec(
            name="opencode",
            display_name="OpenCode",
            launch_script="start_opencode.py",
            cli_candidates=("opencode", "opencode.cmd"),
            install_hint="npm install -g opencode-ai",
            adapter="engines.start_opencode:OpenCodeEngine",
            session_id_fields=("sessionID",),
        ),
        EngineSpec(
            name="codex",
            display_name="Codex",
            launch_script="start_codex.py",
            cli_candidates=("codex", "codex.cmd"),
            install_hint="npm install -g @openai/codex",
            adapter="engines.start_codex:CodexEngine",
            session_id_fields=("thread_id",),
        ),
        EngineSpec(
            name="codebuddy",
            display_name="CodeBuddy",
            launch_script="start_codebuddy.py",
            cli_candidates=("codebuddy", "codebuddy.cmd"),
            install_hint="npm install -g @tencent-ai/codebuddy-code",
            adapter="engines.start_codebuddy:CodeBuddyEngine",
            session_id_fields=("session_id", "sessionId"),
        ),
        EngineSpec(
            name="antigravity",
            display_name="Antigravity",
            launch_script="start_antigravity.py",
            cli_candidates=("agy", "agy.cmd", "agy.exe"),
            install_hint="Follow https://antigravity.google/docs/cli to install agy",
            adapter="engines.start_antigravity:AntigravityEngine",
            session_id_fields=(
                "session_id",
                "sessionId",
                "conversationId",
                "conversation_id",
            ),
            aliases=("agy",),
        ),
    )
}

#: Alias → canonical name. Lookups (CLI first-arg, config default_engine,
#: require_engine_cli) accept either spelling, plus the legacy retired-engine
#: spellings in _LEGACY_ALIASES.
ALIASES: dict[str, str] = {
    alias: spec.name for spec in ENGINES.values() for alias in spec.aliases
}
ALIASES.update(_LEGACY_ALIASES)


def normalize_engine_name(name: str) -> str:
    """Normalizes an engine identifier or alias to its canonical name."""
    cleaned = (name or "").strip().lower()
    return ALIASES.get(cleaned, cleaned)


def get_spec(name_or_alias: str) -> EngineSpec | None:
    """The spec for a canonical name or alias, or None when unknown."""
    return ENGINES.get(normalize_engine_name(name_or_alias))


def engine_names() -> frozenset[str]:
    """Every canonical engine name — the replacement for hand-copied lists."""
    return frozenset(ENGINES)
