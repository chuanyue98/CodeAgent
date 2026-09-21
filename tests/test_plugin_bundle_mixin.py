"""Antigravity 的技能分发：技能打包成单个原生插件并在 config 里启用。

agy 既不认 Claude 风格的 ``skills/`` 目录也没有插件市场，技能要包成
``plugins/codeagent/`` 这一个插件；这里把插件形状和启用标志的增删钉住。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engine_base.plugin_bundle_mixin import (  # noqa: E402
    BUNDLE_NAME,
    _PluginBundleMixin,
)


class FakeEngine(_PluginBundleMixin):
    def __init__(self, config_dir: Path, skills: list[tuple[str, Path]]):
        self._config_dir = config_dir
        self._skills = skills

    def _get_plugin_config_dir(self) -> Path:
        return self._config_dir

    def resolve_skill_sources(self) -> list[tuple[str, Path]]:
        return self._skills

    def _create_skill_link(self, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(source, target_is_directory=True)


def _make_skill(root: Path, name: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    return skill_dir


@pytest.fixture
def engine(tmp_path):
    src = tmp_path / "skills"
    skills = [
        ("task-authoring", _make_skill(src, "task-authoring")),
        ("commit-message", _make_skill(src, "commit-message")),
    ]
    return FakeEngine(tmp_path / "config", skills)


def _config(engine) -> dict:
    return json.loads(
        (engine._get_plugin_config_dir() / "config.json").read_text(encoding="utf-8")
    )


def test_bundle_declares_itself_with_a_plugin_json(engine):
    assert engine.ensure_plugin_bundle() is True

    bundle = engine._get_plugin_config_dir() / "plugins" / BUNDLE_NAME
    assert json.loads((bundle / "plugin.json").read_text(encoding="utf-8")) == {
        "name": BUNDLE_NAME
    }


def test_skills_are_linked_into_the_bundle(engine):
    engine.ensure_plugin_bundle()

    skills_dir = engine._get_plugin_config_dir() / "plugins" / BUNDLE_NAME / "skills"
    link = skills_dir / "task-authoring"
    assert link.is_symlink(), "技能要链接过去，改源文件下次启动即生效"
    assert (link / "SKILL.md").exists()
    assert sorted(p.name for p in skills_dir.iterdir()) == [
        "commit-message",
        "task-authoring",
    ]


def test_bundle_is_enabled_in_the_config(engine):
    engine.ensure_plugin_bundle()

    assert _config(engine)["plugins"][BUNDLE_NAME] == {"enabled": True}


def test_enabling_keeps_the_users_own_plugins(engine):
    path = engine._get_plugin_config_dir() / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "plugins": {"superpowers": {"enabled": True}},
                "userSettings": {"remoteControlHostname": "box"},
            }
        ),
        encoding="utf-8",
    )

    engine.ensure_plugin_bundle()

    config = _config(engine)
    assert config["plugins"]["superpowers"] == {"enabled": True}
    assert config["userSettings"] == {"remoteControlHostname": "box"}


def test_cleanup_removes_only_our_entry(engine):
    path = engine._get_plugin_config_dir() / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"plugins": {"superpowers": {"enabled": True}}}), encoding="utf-8"
    )
    engine.ensure_plugin_bundle()

    engine.cleanup_plugin_bundle()

    assert _config(engine)["plugins"] == {"superpowers": {"enabled": True}}


def test_cleanup_without_a_config_writes_nothing(engine):
    engine.cleanup_plugin_bundle()

    assert not (engine._get_plugin_config_dir() / "config.json").exists()


def test_a_group_without_skills_disables_a_previous_bundle(tmp_path):
    config_dir = tmp_path / "config"
    src = tmp_path / "skills"
    FakeEngine(config_dir, [("a", _make_skill(src, "a"))]).ensure_plugin_bundle()

    empty = FakeEngine(config_dir, [])
    assert empty.ensure_plugin_bundle() is False
    assert BUNDLE_NAME not in _config(empty).get("plugins", {})


def test_a_corrupt_config_is_replaced_rather_than_crashing(engine):
    path = engine._get_plugin_config_dir() / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")

    engine.ensure_plugin_bundle()

    assert _config(engine)["plugins"][BUNDLE_NAME] == {"enabled": True}
