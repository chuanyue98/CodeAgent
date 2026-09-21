"""CodeBuddy 的技能分发：本地插件市场的生成、注册与撤销。

CodeBuddy 不认 Claude 风格的 ``skills/`` 目录，技能要包成插件经市场分发；
这里把市场的形状和 ``--channels`` 的拼法钉住。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engine_base.marketplace_mixin import (  # noqa: E402
    MARKETPLACE_NAME,
    _MarketplaceMixin,
)


class FakeEngine(_MarketplaceMixin):
    """只带市场能力的最小引擎，避免把整个 BaseEngine 拖进来。"""

    def __init__(self, home: Path, skills: list[tuple[str, Path]]):
        self._home = home
        self._skills = skills

    def _get_marketplace_root(self) -> Path:
        return self._home / ".tmp" / "marketplaces" / MARKETPLACE_NAME

    def _get_known_marketplaces_path(self) -> Path:
        return self._home / "plugins" / "known_marketplaces.json"

    def resolve_skill_sources(self) -> list[tuple[str, Path]]:
        return self._skills


def _make_skill(root: Path, name: str, description: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return skill_dir


@pytest.fixture
def engine(tmp_path):
    home = tmp_path / "home"
    src = tmp_path / "skills"
    skills = [
        ("task-authoring", _make_skill(src, "task-authoring", "写任务模板")),
        ("commit-message", _make_skill(src, "commit-message", "写提交信息")),
    ]
    return FakeEngine(home, skills)


def test_marketplace_manifest_lists_every_skill_as_a_plugin(engine):
    names = engine.ensure_marketplace()

    assert names == ["task-authoring", "commit-message"]
    manifest = json.loads(
        (
            engine._get_marketplace_root() / ".codebuddy-plugin" / "marketplace.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["name"] == MARKETPLACE_NAME
    entry = manifest["plugins"][0]
    assert entry["name"] == "task-authoring"
    # 技能目录既是插件本体也是它声明的技能来源，两个字段都得指过去。
    assert entry["source"] == "./plugins/task-authoring"
    assert entry["skills"] == ["./plugins/task-authoring"]


def test_plugin_description_comes_from_the_skill_frontmatter(engine):
    engine.ensure_marketplace()

    manifest = json.loads(
        (
            engine._get_marketplace_root() / ".codebuddy-plugin" / "marketplace.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["plugins"][0]["description"] == "写任务模板"


def test_skills_are_copied_into_the_marketplace(engine):
    """CodeBuddy 会拒绝 resolve 后跑出市场根的插件源，所以只能复制不能链接。"""
    engine.ensure_marketplace()

    plugin = engine._get_marketplace_root() / "plugins" / "task-authoring"
    assert plugin.is_dir() and not plugin.is_symlink()
    assert (plugin / "SKILL.md").exists()


def test_rerunning_rebuilds_instead_of_failing(engine):
    """第二次启动不能因为目录已存在就炸，整个 plugins/ 由我们独占，重建即可。"""
    engine.ensure_marketplace()

    assert engine.ensure_marketplace() == ["task-authoring", "commit-message"]
    assert (
        engine._get_marketplace_root() / "plugins" / "task-authoring" / "SKILL.md"
    ).exists()


def test_a_skill_dropped_from_the_group_is_gone_on_the_next_run(tmp_path):
    src = tmp_path / "skills"
    both = [
        ("task-authoring", _make_skill(src, "task-authoring", "写任务模板")),
        ("commit-message", _make_skill(src, "commit-message", "写提交信息")),
    ]
    home = tmp_path / "home"
    FakeEngine(home, both).ensure_marketplace()

    FakeEngine(home, both[:1]).ensure_marketplace()

    plugins_dir = FakeEngine(home, both)._get_marketplace_root() / "plugins"
    assert sorted(p.name for p in plugins_dir.iterdir()) == ["task-authoring"]


def test_registration_uses_a_directory_source(engine):
    engine.ensure_marketplace()

    known = json.loads(
        engine._get_known_marketplaces_path().read_text(encoding="utf-8")
    )
    entry = known[MARKETPLACE_NAME]
    assert entry["type"] == "directory"
    assert entry["source"]["path"] == str(engine._get_marketplace_root())
    # 本地市场没有上游可拉，自动更新必须关掉。
    assert entry["autoUpdate"] is False
    assert entry["isBuiltIn"] is False


def test_registration_keeps_the_engines_own_marketplaces(engine):
    path = engine._get_known_marketplaces_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"codebuddy-plugins-official": {"isBuiltIn": True}}),
        encoding="utf-8",
    )

    engine.ensure_marketplace()

    known = json.loads(path.read_text(encoding="utf-8"))
    assert "codebuddy-plugins-official" in known
    assert MARKETPLACE_NAME in known


def test_cleanup_removes_only_our_entry(engine):
    path = engine._get_known_marketplaces_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"codebuddy-plugins-official": {"isBuiltIn": True}}),
        encoding="utf-8",
    )
    engine.ensure_marketplace()

    engine.cleanup_marketplace()

    known = json.loads(path.read_text(encoding="utf-8"))
    assert known == {"codebuddy-plugins-official": {"isBuiltIn": True}}


def test_cleanup_drops_the_file_when_we_were_its_only_entry(engine):
    engine.ensure_marketplace()

    engine.cleanup_marketplace()

    assert not engine._get_known_marketplaces_path().exists()


def test_cleanup_is_safe_when_nothing_was_registered(engine):
    engine.cleanup_marketplace()  # 不应抛异常


def test_a_group_without_skills_unregisters_the_previous_marketplace(tmp_path):
    home = tmp_path / "home"
    src = tmp_path / "skills"
    with_skills = FakeEngine(home, [("a", _make_skill(src, "a", "d"))])
    with_skills.ensure_marketplace()

    empty = FakeEngine(home, [])
    assert empty.ensure_marketplace() == []
    assert not empty._get_known_marketplaces_path().exists()


def test_channel_args_name_the_marketplace(engine):
    args = engine.channel_args(["task-authoring", "commit-message"])

    assert args == [
        "--channels",
        f"plugin:task-authoring@{MARKETPLACE_NAME},"
        f"plugin:commit-message@{MARKETPLACE_NAME}",
    ]


def test_channel_args_are_empty_without_plugins(engine):
    """没有插件时不能传 ``--channels ''``，那会被当成一个空频道名。"""
    assert engine.channel_args([]) == []
