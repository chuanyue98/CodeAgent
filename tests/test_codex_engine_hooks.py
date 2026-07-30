"""Tests for codex hook support in the launcher engine.

The event names and TOML shape asserted here were confirmed live against
codex-cli 0.142.5 by writing a config and reading it back through the
app-server's ``hooks/list`` method — codex accepts the same PascalCase event
names and the same matcher-group structure as Claude, expressed in TOML.
Project-local hooks additionally require the project to be marked trusted in
the user-level ``~/.codex/config.toml``, or codex drops them without an error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engines.start_codex import CodexEngine


@pytest.fixture
def engine():
    return CodexEngine()


def test_codex_maps_canonical_events_to_codex_names(engine):
    assert engine.EVENT_MAP == {
        "before_tool": "PreToolUse",
        "after_tool": "PostToolUse",
    }


def test_settings_manager_uses_the_codex_event_map(engine):
    assert engine.settings_manager.event_map["before_tool"] == "PreToolUse"


def test_warns_when_the_project_is_not_trusted(engine, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    user_config = tmp_path / "codex_home" / "config.toml"
    user_config.parent.mkdir()
    user_config.write_text('model = "x"\n', encoding="utf-8")
    monkeypatch.setattr(engine, "_get_user_config_path", lambda: user_config)

    engine.warn_if_project_untrusted()

    out = capsys.readouterr().out
    assert "not a trusted project" in out
    assert 'trust_level = "trusted"' in out


def test_stays_quiet_when_the_project_is_trusted(engine, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    project = Path(tmp_path).resolve()
    user_config = tmp_path / "codex_home" / "config.toml"
    user_config.parent.mkdir()
    user_config.write_text(
        f'[projects."{str(project).replace(chr(92), chr(92) * 2)}"]\n'
        'trust_level = "trusted"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(engine, "_get_user_config_path", lambda: user_config)

    engine.warn_if_project_untrusted()

    assert capsys.readouterr().out == ""


def test_warns_when_the_user_config_is_missing(engine, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        engine, "_get_user_config_path", lambda: tmp_path / "nope" / "config.toml"
    )

    engine.warn_if_project_untrusted()

    assert "not a trusted project" in capsys.readouterr().out


def test_warns_when_a_different_project_is_the_trusted_one(
    engine, tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    user_config = tmp_path / "codex_home" / "config.toml"
    user_config.parent.mkdir()
    user_config.write_text(
        '[projects."C:\\\\somewhere\\\\else"]\ntrust_level = "trusted"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(engine, "_get_user_config_path", lambda: user_config)

    engine.warn_if_project_untrusted()

    assert "not a trusted project" in capsys.readouterr().out
