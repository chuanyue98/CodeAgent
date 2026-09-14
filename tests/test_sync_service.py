from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from core.link_manager import LinkManager
from core.services import sync_service
from core.services.sync_service import (
    SyncItem,
    render_block,
    replace_block,
    strip_block,
    synced_group,
)


class _FakeResources:
    """代替按组解析资源的引擎，测试不依赖本机 config.json。"""

    def __init__(self, group, standards, skills):
        self.group = group or "common"
        self.full_config = {"groups": {"common": {}, "work": {}}}
        self.link_manager = LinkManager()
        self._standards = standards
        self._skills = skills

    def assemble_standards(self):
        return self._standards

    def resolve_skill_sources(self):
        return list(self._skills)


@pytest.fixture
def skill_source(tmp_path):
    source = tmp_path / "bundled" / "commit-message"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: commit-message\n---\n", encoding="utf-8"
    )
    return source


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return home


def _use_resources(monkeypatch, standards="STANDARDS_BODY", skills=()):
    monkeypatch.setattr(
        sync_service,
        "_GroupEngine",
        lambda group: _FakeResources(group, standards, skills),
    )


def _by(items, engine, kind):
    return [item for item in items if item.engine == engine and item.kind == kind]


# --- managed block -------------------------------------------------------


def test_block_is_appended_after_user_content_and_replaced_in_place():
    user = "# 我的规则\n\n别用 tab。\n"

    first = replace_block(user, render_block("common", "V1"))
    second = replace_block(first, render_block("work", "V2"))

    assert first.startswith(
        user.rstrip("\n") + "\n\n<!-- codeagent:begin group=common -->"
    )
    assert "V1" not in second and "V2" in second
    assert second.count("codeagent:begin") == 1
    assert strip_block(second) == user


def test_stripping_a_file_that_only_held_the_block_leaves_it_empty():
    assert strip_block(render_block("common", "V1")) == ""


def test_synced_group_reads_the_marker(tmp_path):
    path = tmp_path / "AGENTS.md"
    assert synced_group(path) is None

    path.write_text("intro\n\n" + render_block("work", "body"), encoding="utf-8")

    assert synced_group(path) == "work"


# --- sync ----------------------------------------------------------------


def test_sync_writes_every_engine_and_is_idempotent(monkeypatch, home, skill_source):
    _use_resources(monkeypatch, skills=[("commit-message", skill_source)])

    group, items = sync_service.sync(home=home)

    assert group == "common"
    targets = sync_service.engine_targets(home)
    for target in targets.values():
        assert "STANDARDS_BODY" in target.memory_file.read_text(encoding="utf-8")
        assert (target.skills_dir / "commit-message" / "SKILL.md").exists()
    assert {item.action for item in items} == {"write"}
    assert (
        targets["antigravity"].memory_file == home / ".gemini" / "config" / "GEMINI.md"
    )

    _, again = sync_service.sync(home=home)
    assert {item.action for item in again} == {"unchanged"}


def test_sync_keeps_user_content_and_remove_takes_only_our_part(
    monkeypatch, home, skill_source
):
    claude_md = home / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True)
    claude_md.write_text("# 我自己的规则\n", encoding="utf-8")
    _use_resources(monkeypatch, skills=[("commit-message", skill_source)])
    sync_service.sync(engines=["claude"], home=home)

    _, items = sync_service.sync(engines=["claude"], remove=True, home=home)

    assert claude_md.read_text(encoding="utf-8") == "# 我自己的规则\n"
    assert not (home / ".claude" / "skills" / "commit-message").exists()
    assert {(item.kind, item.action) for item in items} == {
        ("standards", "remove"),
        ("skill", "remove"),
    }


def test_sync_never_replaces_a_user_owned_skill(monkeypatch, home, skill_source):
    own = home / ".claude" / "skills" / "commit-message"
    own.mkdir(parents=True)
    (own / "SKILL.md").write_text("mine", encoding="utf-8")
    _use_resources(monkeypatch, skills=[("commit-message", skill_source)])

    _, items = sync_service.sync(engines=["claude"], home=home)

    assert _by(items, "claude", "skill")[0].action == "conflict"
    assert (own / "SKILL.md").read_text(encoding="utf-8") == "mine"


def test_dry_run_writes_nothing(monkeypatch, home, skill_source):
    _use_resources(monkeypatch, skills=[("commit-message", skill_source)])

    _, items = sync_service.sync(dry_run=True, home=home)

    assert {item.action for item in items} == {"write"}
    assert not any(home.iterdir())


def test_unknown_group_is_rejected(monkeypatch, home):
    _use_resources(monkeypatch)

    with pytest.raises(ValueError, match="nope"):
        sync_service.sync(group="nope", home=home)


def test_codex_home_is_respected(monkeypatch, home, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))

    target = sync_service.engine_targets(home)["codex"]

    assert target.memory_file == tmp_path / "codex-home" / "AGENTS.md"
    assert target.skills_dir == tmp_path / "codex-home" / "skills"


def test_codebuddy_config_dir_is_respected(monkeypatch, home, tmp_path):
    monkeypatch.setenv("CODEBUDDY_CONFIG_DIR", str(tmp_path / "cb"))

    target = sync_service.engine_targets(home)["codebuddy"]

    assert target.memory_file == tmp_path / "cb" / "CODEBUDDY.md"


def test_is_synced_matches_engine_and_group(monkeypatch, home):
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    _use_resources(monkeypatch)
    sync_service.sync(group="work", engines=["opencode"], home=home)

    assert sync_service.is_synced("opencode", "work")
    assert not sync_service.is_synced("opencode", "common")
    assert not sync_service.is_synced("claude", "work")


# --- CLI -----------------------------------------------------------------


def test_cli_reports_each_item_and_fails_on_errors(tmp_path, monkeypatch):
    from core.cli.main import cli

    monkeypatch.chdir(tmp_path)
    items = [
        SyncItem("claude", "standards", str(Path("/h/.claude/CLAUDE.md")), "write"),
        SyncItem("claude", "skill", "commit-message", "failed"),
    ]
    with patch.object(sync_service, "sync", return_value=("common", items)) as mocked:
        result = CliRunner().invoke(cli, ["sync", "--engine", "claude", "--dry-run"])

    mocked.assert_called_once_with(
        group=None, engines=["claude"], remove=False, dry_run=True
    )
    assert "CLAUDE.md" in result.output
    assert "skills/commit-message" in result.output
    assert result.exit_code == 1


def test_cli_turns_value_errors_into_exit_code_1(tmp_path, monkeypatch):
    from core.cli.main import cli

    monkeypatch.chdir(tmp_path)
    with patch.object(sync_service, "sync", side_effect=ValueError("bad group")):
        result = CliRunner().invoke(cli, ["sync", "--group", "x"])

    assert result.exit_code == 1
    assert "bad group" in result.output
