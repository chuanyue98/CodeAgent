"""CodeBuddy 的技能分发：本地 inline 插件的生成、挂载与清理。

CodeBuddy 不认 Claude 风格的 ``skills/`` 目录，技能要包成插件；这里把插件的
形状和 ``CODEBUDDY_PLUGIN_DIRS`` 的拼法钉住。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engine_base.plugin_dir_mixin import (  # noqa: E402
    PLUGIN_DIRS_ENV,
    PLUGIN_NAME,
    _PluginDirMixin,
)


class FakeEngine(_PluginDirMixin):
    """只带插件挂载能力的最小引擎，避免把整个 BaseEngine 拖进来。"""

    def __init__(
        self,
        home: Path,
        skills: list[tuple[str, Path]],
        plugins: list[dict] | None = None,
    ):
        self._home = home
        self._skills = skills
        self._plugins = plugins or []

    def _get_plugin_dir_root(self) -> Path:
        return self._home / ".tmp" / "plugins"

    def resolve_skill_sources(self) -> list[tuple[str, Path]]:
        return self._skills

    def get_plugins_to_mount(self) -> list[dict]:
        return self._plugins


def _make_skill(root: Path, name: str, description: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return skill_dir


@pytest.fixture
def project(tmp_path) -> Path:
    path = tmp_path / "project"
    path.mkdir()
    return path


@pytest.fixture
def engine(tmp_path):
    home = tmp_path / "home"
    src = tmp_path / "skills"
    skills = [
        ("task-authoring", _make_skill(src, "task-authoring", "写任务模板")),
        ("commit-message", _make_skill(src, "commit-message", "写提交信息")),
    ]
    return FakeEngine(home, skills)


def test_every_skill_lands_in_the_plugins_skills_dir(engine, project):
    root = engine.ensure_plugin_dir(project)

    assert root is not None
    assert sorted(p.name for p in (root / "skills").iterdir()) == [
        "commit-message",
        "task-authoring",
    ]
    assert (root / "skills" / "task-authoring" / "SKILL.md").exists()


def test_manifest_names_the_plugin_and_leaves_skills_to_discovery(engine, project):
    """manifest 不声明 skills，引擎自己扫 skills/；声明了反而要逐条对路径。"""
    root = engine.ensure_plugin_dir(project)

    manifest = json.loads(
        (root / ".codebuddy-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == PLUGIN_NAME
    assert manifest["version"] == "1.0.0"
    assert "skills" not in manifest


def test_skills_are_copied_not_linked(engine, project):
    root = engine.ensure_plugin_dir(project)

    skill = root / "skills" / "task-authoring"
    assert skill.is_dir() and not skill.is_symlink()


def test_rerunning_rebuilds_instead_of_failing(engine, project):
    first = engine.ensure_plugin_dir(project)

    assert engine.ensure_plugin_dir(project) == first
    assert (first / "skills" / "task-authoring" / "SKILL.md").exists()


def test_a_skill_dropped_from_the_group_is_gone_on_the_next_run(tmp_path, project):
    src = tmp_path / "skills"
    both = [
        ("task-authoring", _make_skill(src, "task-authoring", "写任务模板")),
        ("commit-message", _make_skill(src, "commit-message", "写提交信息")),
    ]
    home = tmp_path / "home"
    FakeEngine(home, both).ensure_plugin_dir(project)

    root = FakeEngine(home, both[:1]).ensure_plugin_dir(project)

    assert [p.name for p in (root / "skills").iterdir()] == ["task-authoring"]


def test_two_projects_get_their_own_plugin_dirs(tmp_path, engine, project):
    other = tmp_path / "other-project"
    other.mkdir()

    assert engine.ensure_plugin_dir(project) != engine.ensure_plugin_dir(other)


def test_cleanup_leaves_the_other_projects_plugin_dir_alone(tmp_path, engine, project):
    other = tmp_path / "other-project"
    other.mkdir()
    engine.ensure_plugin_dir(project)
    kept = engine.ensure_plugin_dir(other)

    engine.cleanup_plugin_dir(project)

    assert not engine._get_plugin_dir(project).exists()
    assert kept.exists()


def test_cleanup_is_safe_when_nothing_was_mounted(engine, project):
    engine.cleanup_plugin_dir(project)  # 不应抛异常


def test_a_group_without_skills_mounts_nothing_and_clears_the_last_run(
    tmp_path, project
):
    home = tmp_path / "home"
    src = tmp_path / "skills"
    FakeEngine(home, [("a", _make_skill(src, "a", "d"))]).ensure_plugin_dir(project)

    empty = FakeEngine(home, [])
    assert empty.ensure_plugin_dir(project) is None
    assert not empty._get_plugin_dir(project).exists()


def test_env_points_the_engine_at_the_plugin_dir(engine, project):
    root = engine.ensure_plugin_dir(project)

    assert engine.plugin_dir_env(root) == {PLUGIN_DIRS_ENV: str(root)}


def test_env_is_empty_without_anything_to_mount(engine):
    """没挂插件时不能塞个空串，那会被当成一个空目录去加载。"""
    assert engine.plugin_dir_env(None) == {}


def test_group_plugins_follow_the_skills_plugin(tmp_path, project):
    """项目组声明的插件跟在技能插件后面，顺序决定同名技能谁先被看到。"""
    home = tmp_path / "home"
    src = tmp_path / "skills"
    superpowers = tmp_path / "superpowers"
    superpowers.mkdir()
    engine = FakeEngine(
        home,
        [("a", _make_skill(src, "a", "d"))],
        [{"name": "superpowers", "_plugin_dir": str(superpowers)}],
    )
    root = engine.ensure_plugin_dir(project)

    assert engine.plugin_dir_env(root) == {
        PLUGIN_DIRS_ENV: os.pathsep.join([str(root), str(superpowers)])
    }


def test_group_plugins_mount_even_without_skills(tmp_path, project):
    home = tmp_path / "home"
    superpowers = tmp_path / "superpowers"
    superpowers.mkdir()
    engine = FakeEngine(
        home, [], [{"name": "superpowers", "_plugin_dir": str(superpowers)}]
    )

    assert engine.ensure_plugin_dir(project) is None
    assert engine.plugin_dir_env(None) == {PLUGIN_DIRS_ENV: str(superpowers)}


def test_a_plugin_that_no_longer_exists_is_skipped(tmp_path, project):
    """submodule 没 init 时插件目录是空的甚至不存在，不能把路径原样塞给引擎。"""
    home = tmp_path / "home"
    engine = FakeEngine(
        home, [], [{"name": "superpowers", "_plugin_dir": str(tmp_path / "gone")}]
    )

    assert engine.plugin_dir_env(None) == {}
