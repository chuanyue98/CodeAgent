from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from core.link_manager import LinkManager
from core.services import sync_service
from core.services.sync_service import (
    STANDARDS_FILENAME,
    SyncItem,
    render_block,
    replace_block,
    standards_file,
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


@pytest.fixture
def project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    return project


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


def test_standards_file_defaults_to_the_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert standards_file() == tmp_path / STANDARDS_FILENAME
    assert standards_file(tmp_path / "elsewhere") == (
        tmp_path / "elsewhere" / STANDARDS_FILENAME
    )


# --- sync ----------------------------------------------------------------


def test_sync_writes_one_agents_md_and_skills_for_every_engine(
    monkeypatch, home, project, skill_source
):
    """规范只写一个文件、只报一条；技能仍然每个引擎一份。"""
    _use_resources(monkeypatch, skills=[("commit-message", skill_source)])

    group, items = sync_service.sync(root=project, home=home)

    assert group == "common"
    assert (project / STANDARDS_FILENAME).read_text(encoding="utf-8").count(
        "STANDARDS_BODY"
    ) == 1
    # 不再 fan-out 到各引擎自己的文件名。
    for name in ("CLAUDE.md", "CODEBUDDY.md", "GEMINI.md"):
        assert not (project / name).exists()

    standards_items = [item for item in items if item.kind == "standards"]
    assert len(standards_items) == 1
    assert standards_items[0].engine == ""
    assert standards_items[0].name == STANDARDS_FILENAME

    targets = sync_service.engine_targets(home)
    for target in targets.values():
        assert (target.skills_dir / "commit-message" / "SKILL.md").exists()
    assert {item.action for item in items} == {"write"}

    _, again = sync_service.sync(root=project, home=home)
    assert {item.action for item in again} == {"unchanged"}


def test_sync_keeps_agents_md_content_and_remove_takes_only_our_part(
    monkeypatch, home, project, skill_source
):
    agents_md = project / STANDARDS_FILENAME
    agents_md.write_text("# 我自己的规则\n", encoding="utf-8")
    _use_resources(monkeypatch, skills=[("commit-message", skill_source)])
    sync_service.sync(engines=["claude"], root=project, home=home)

    assert "# 我自己的规则" in agents_md.read_text(encoding="utf-8")

    _, items = sync_service.sync(
        engines=["claude"], remove=True, root=project, home=home
    )

    assert agents_md.read_text(encoding="utf-8") == "# 我自己的规则\n"
    assert not (home / ".claude" / "skills" / "commit-message").exists()
    assert [(item.kind, item.action) for item in items] == [
        ("standards", "remove"),
        ("skill", "remove"),
    ]


def test_remove_deletes_an_agents_md_that_only_held_our_block(
    monkeypatch, home, project
):
    """项目里原本没有 AGENTS.md 时，还原就该还原成没有，而不是留个空文件。"""
    _use_resources(monkeypatch)
    sync_service.sync(root=project, home=home)
    assert (project / STANDARDS_FILENAME).exists()

    sync_service.sync(remove=True, root=project, home=home)

    assert not (project / STANDARDS_FILENAME).exists()


def test_sync_never_replaces_a_user_owned_skill(
    monkeypatch, home, project, skill_source
):
    own = home / ".claude" / "skills" / "commit-message"
    own.mkdir(parents=True)
    (own / "SKILL.md").write_text("mine", encoding="utf-8")
    _use_resources(monkeypatch, skills=[("commit-message", skill_source)])

    _, items = sync_service.sync(engines=["claude"], root=project, home=home)

    assert _by(items, "claude", "skill")[0].action == "conflict"
    assert (own / "SKILL.md").read_text(encoding="utf-8") == "mine"


def test_dry_run_writes_nothing(monkeypatch, home, project, skill_source):
    _use_resources(monkeypatch, skills=[("commit-message", skill_source)])

    _, items = sync_service.sync(dry_run=True, root=project, home=home)

    assert {item.action for item in items} == {"write"}
    assert not any(home.iterdir())
    assert not any(project.iterdir())


def test_unknown_group_is_rejected(monkeypatch, home, project):
    _use_resources(monkeypatch)

    with pytest.raises(ValueError, match="nope"):
        sync_service.sync(group="nope", root=project, home=home)


def test_unknown_scope_is_rejected(monkeypatch, home, project):
    _use_resources(monkeypatch)

    with pytest.raises(ValueError, match="Unknown scope"):
        sync_service.sync(scope="galaxy", root=project, home=home)


def test_user_scope_still_writes_each_engines_user_level_config(
    monkeypatch, home, project
):
    """`ca sync --user` 保留旧位置，用来清理历史遗留的托管块。"""
    _use_resources(monkeypatch)

    _, items = sync_service.sync(scope="user", engines=["claude"], home=home)

    memory_file = home / ".claude" / "CLAUDE.md"
    assert "STANDARDS_BODY" in memory_file.read_text(encoding="utf-8")
    assert not (project / STANDARDS_FILENAME).exists()
    assert _by(items, "", "standards")[0].name == str(memory_file)


def test_codex_home_is_respected(monkeypatch, home, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))

    target = sync_service.engine_targets(home)["codex"]

    assert target.memory_file == tmp_path / "codex-home" / "AGENTS.md"
    assert target.skills_dir == tmp_path / "codex-home" / "skills"


def test_codebuddy_config_dir_is_respected(monkeypatch, home, tmp_path):
    monkeypatch.setenv("CODEBUDDY_CONFIG_DIR", str(tmp_path / "cb"))

    target = sync_service.engine_targets(home)["codebuddy"]

    assert target.memory_file == tmp_path / "cb" / "CODEBUDDY.md"


# --- CLI -----------------------------------------------------------------


def test_cli_reports_each_item_and_fails_on_errors(tmp_path, monkeypatch):
    from core.cli.main import cli

    monkeypatch.chdir(tmp_path)
    items = [
        SyncItem("", "standards", "AGENTS.md", "write"),
        SyncItem("claude", "skill", "commit-message", "failed"),
    ]
    with patch.object(sync_service, "sync", return_value=("common", items)) as mocked:
        result = CliRunner().invoke(cli, ["sync", "--engine", "claude", "--dry-run"])

    mocked.assert_called_once_with(
        group=None,
        engines=["claude"],
        remove=False,
        dry_run=True,
        scope="project",
        root=None,
    )
    assert "AGENTS.md" in result.output
    assert "skills/commit-message" in result.output
    assert result.exit_code == 1


def test_cli_user_flag_changes_the_scope(tmp_path, monkeypatch):
    from core.cli.main import cli

    monkeypatch.chdir(tmp_path)
    with patch.object(sync_service, "sync", return_value=("common", [])) as mocked:
        CliRunner().invoke(cli, ["sync", "--user"])

    assert mocked.call_args.kwargs["scope"] == "user"


def test_cli_turns_value_errors_into_exit_code_1(tmp_path, monkeypatch):
    from core.cli.main import cli

    monkeypatch.chdir(tmp_path)
    with patch.object(sync_service, "sync", side_effect=ValueError("bad group")):
        result = CliRunner().invoke(cli, ["sync", "--group", "x"])

    assert result.exit_code == 1
    assert "bad group" in result.output


def test_cli_project_option_points_the_standards_at_another_directory(
    tmp_path, monkeypatch
):
    from core.cli.main import cli

    monkeypatch.chdir(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    with patch.object(sync_service, "sync", return_value=("common", [])) as mocked:
        CliRunner().invoke(cli, ["sync", "--project", str(elsewhere)])

    assert mocked.call_args.kwargs["root"] == Path(elsewhere)
