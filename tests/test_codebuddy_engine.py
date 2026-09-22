from __future__ import annotations

import json
from pathlib import Path

import pytest

from engines.start_codebuddy import CodeBuddyEngine


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEBUDDY_CONFIG_DIR", str(tmp_path / "codebuddy"))
    return CodeBuddyEngine()


def test_build_command_passes_native_args_through(engine):
    cmd = engine.build_command("hi", non_interactive=False, passthrough=["-r"])

    assert cmd == ["codebuddy", "--permission-mode", "auto", "-r", "hi"]


def _write_known(engine, payload: dict) -> Path:
    path = engine._get_codebuddy_home() / "plugins" / "known_marketplaces.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_legacy_marketplace_registration_is_dropped(engine):
    path = _write_known(
        engine, {"codeagent-local": {"type": "directory"}, "official": {}}
    )

    engine.drop_legacy_marketplace()

    assert json.loads(path.read_text(encoding="utf-8")) == {"official": {}}


def test_dropping_the_last_entry_removes_the_file(engine):
    path = _write_known(engine, {"codeagent-local": {"type": "directory"}})

    engine.drop_legacy_marketplace()

    assert not path.exists()


def test_the_engines_own_marketplaces_are_left_alone(engine):
    path = _write_known(engine, {"official": {"isBuiltIn": True}})

    engine.drop_legacy_marketplace()

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "official": {"isBuiltIn": True}
    }


def test_the_legacy_marketplace_directory_goes_too(engine):
    stale = engine._get_codebuddy_home() / ".tmp" / "marketplaces" / "codeagent-local"
    stale.mkdir(parents=True)
    (stale / "marketplace.json").write_text("{}", encoding="utf-8")

    engine.drop_legacy_marketplace()

    assert not stale.exists()


def test_dropping_is_safe_on_a_clean_machine(engine):
    engine.drop_legacy_marketplace()  # 不应抛异常
