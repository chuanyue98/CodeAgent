"""Tests for the declarative engine registry (AUDIT-002) and its consumers.

The registry exists so "which engines exist" is declared exactly once.
These tests pin the derived views (constants, CLI map, doctor tables,
runner construction, session-id fields) to the registry, so a new EngineSpec
entry cannot silently diverge from any of them.
"""

from __future__ import annotations

import click
import pytest

from core.engine_registry import ALIASES, ENGINES, get_spec, normalize_engine_name


def test_registry_covers_all_five_engines():
    assert set(ENGINES) == {"claude", "opencode", "codex", "codebuddy", "antigravity"}


def test_every_spec_is_complete():
    for name, spec in ENGINES.items():
        assert spec.name == name
        assert spec.display_name
        assert spec.launch_script.startswith("start_") and spec.launch_script.endswith(
            ".py"
        )
        assert spec.cli_candidates, f"{name} needs at least one CLI candidate"
        assert spec.install_hint, f"{name} needs an install hint for doctor"
        assert ":" in spec.adapter, f"{name} adapter must be 'module:Class'"
        assert spec.session_id_fields, f"{name} needs chat session-id fields"


def test_launch_scripts_exist():
    from core.resource_locator import CODE_ROOT

    for spec in ENGINES.values():
        assert (CODE_ROOT / "engines" / spec.launch_script).is_file(), (
            spec.launch_script
        )


def test_alias_normalization():
    assert normalize_engine_name("agy") == "antigravity"
    assert normalize_engine_name("AGY") == "antigravity"
    assert normalize_engine_name("claude") == "claude"
    assert normalize_engine_name("") == ""
    assert normalize_engine_name("nope") == "nope"
    # Every alias resolves to a real engine.
    for canonical in ALIASES.values():
        assert canonical in ENGINES


def test_get_spec_accepts_alias_and_canonical():
    assert get_spec("agy") is get_spec("antigravity")
    assert get_spec("codex") is ENGINES["codex"]
    assert get_spec("unknown-engine") is None


def test_constants_derive_from_registry():
    from core.constants import ENGINES as CONSTANTS_ENGINES
    from core.constants import HEADLESS_ENGINES, MCP_ENGINES, normalize_engine_name

    assert CONSTANTS_ENGINES == frozenset(ENGINES)
    assert HEADLESS_ENGINES == CONSTANTS_ENGINES
    assert MCP_ENGINES == CONSTANTS_ENGINES
    # Live alias and legacy retired-engine spelling both resolve to
    # antigravity instead of erroring.
    assert normalize_engine_name("agy") == "antigravity"
    assert normalize_engine_name("gemini") == "antigravity"


def test_cli_script_map_covers_aliases():
    from pathlib import Path

    from core.engine_registry import engine_names
    from core.resource_locator import CODE_ROOT

    root = CODE_ROOT
    expected = {
        key: str(root / "engines" / spec.launch_script)
        for spec in ENGINES.values()
        for key in (spec.name, *spec.aliases)
    }
    # Reproduce the derivation used in core.cli.main and compare keys.
    # The launch map covers live aliases only — the legacy "gemini" alias
    # exists to normalize old records, not as a launch spelling.
    assert set(expected) == engine_names() | {a for a in ALIASES if a != "gemini"}
    assert Path(expected["agy"]).name == "start_antigravity.py"
    assert "gemini" not in expected


def test_doctor_tables_derive_from_registry():
    from core.doctor import ENGINE_BINARIES, ENGINE_INSTALL_HINTS

    assert set(ENGINE_BINARIES) == set(ENGINES)
    assert set(ENGINE_INSTALL_HINTS) == set(ENGINES)
    for name, spec in ENGINES.items():
        assert ENGINE_BINARIES[name] == list(spec.cli_candidates)
        assert ENGINE_INSTALL_HINTS[name] == spec.install_hint


def test_cli_utils_derive_from_registry():
    from core.cli_utils import (
        ENGINE_CLI_CANDIDATES,
        ENGINE_DISPLAY_NAMES,
        ENGINE_INSTALL_HINTS,
    )

    assert set(ENGINE_CLI_CANDIDATES) == set(ENGINES)
    assert set(ENGINE_INSTALL_HINTS) == set(ENGINES)
    assert set(ENGINE_DISPLAY_NAMES) == set(ENGINES)
    # Antigravity used to install agy.exe on Windows only; POSIX skips it.
    assert "agy" in ENGINE_CLI_CANDIDATES["antigravity"]


def test_runner_session_id_fields_derive_from_registry():
    from core.services.runner_service import _CHAT_SESSION_ID_FIELDS

    assert set(_CHAT_SESSION_ID_FIELDS) == set(ENGINES)
    assert _CHAT_SESSION_ID_FIELDS["codex"] == ("thread_id",)


def test_runner_build_engine_resolves_via_registry():
    import tempfile
    from pathlib import Path

    from core.services.runner_service import TaskRunner

    with tempfile.TemporaryDirectory() as tmp:
        runner = TaskRunner(Path(tmp))
        try:
            engine = runner._build_engine("codex")
            assert type(engine).__name__ == "CodexEngine"
            engine = runner._build_engine("antigravity")
            assert type(engine).__name__ == "AntigravityEngine"
            with pytest.raises(ValueError):
                runner._build_engine("not-an-engine")
        finally:
            runner.close()


def test_batch_run_engine_choice_derives_from_registry():
    from core.cli.commands.tasks import batch_run

    param = next(p for p in batch_run.params if p.name == "engine")
    assert isinstance(param.type, click.Choice)
    assert set(param.type.choices) == set(ENGINES)
