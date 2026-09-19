"""`ca status` 的契约：一屏说清这套体系此刻在为你做什么。

它和 `ca doctor` 分工不同（doctor 查环境是否健康），所以断言的是"信息说清了
没有"，不是"检查项对不对"。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from core.cli.commands.status import _standards_detail
from core.cli.main import cli
from core.engine_registry import get_spec
from core.services.sync_service import engine_targets, render_block


def _write_config(path: Path, registry: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "default_group": "common",
                "language": "en",
                "groups": {
                    "common": {
                        "skills": ["commit-message"],
                        "prompts": ["base"],
                        "hooks": [],
                        "plugins": ["base/superpowers"],
                    },
                    "work": {"skills": [], "prompts": [], "hooks": [], "plugins": []},
                },
                "project_registry": registry,
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def status_env(tmp_path, monkeypatch):
    """把 config、HOME、cwd 都指到 tmp，别读开发者真实的配置与用户级文件。"""
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    config = tmp_path / "config.json"
    _write_config(config, [{"path": str(project), "group": "common"}])

    monkeypatch.setenv("CA_CONFIG_PATH", str(config))
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)
    return project


def test_status_reports_the_group_and_its_resources(status_env):
    result = CliRunner().invoke(cli, ["status"])

    assert result.exit_code == 0, result.output
    for heading in ("Project", "Resources in group common", "Engines"):
        assert heading in result.output
    assert "Resource group" in result.output
    assert "skills 1" in result.output
    assert "prompts 1" in result.output
    assert "plugins 1" in result.output


def test_status_says_so_when_the_directory_is_not_registered(tmp_path, monkeypatch):
    """没登记时 cwd 会落到默认组——那是兜底，不是用户选的组，必须说清。"""
    home = tmp_path / "home"
    home.mkdir()
    config = tmp_path / "config.json"
    _write_config(config, [])
    monkeypatch.setenv("CA_CONFIG_PATH", str(config))
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["status"])

    assert result.exit_code == 0, result.output
    assert "not registered" in result.output
    assert "ca project add" in result.output


def test_status_survives_a_group_that_is_not_defined(tmp_path, monkeypatch, home):
    """分组名来自 registry，可以指向 config.json 里不存在的组。"""
    config = tmp_path / "config.json"
    _write_config(config, [{"path": str(tmp_path), "group": "ghost"}])
    monkeypatch.setenv("CA_CONFIG_PATH", str(config))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["status"])

    assert result.exit_code == 0, result.output
    assert "ghost" in result.output


# --- 每个引擎的规范状态判定 ------------------------------------------------


def test_launch_channel_is_reported_when_nothing_is_synced(home):
    state, detail = _standards_detail(get_spec("claude"), "common")

    assert state == "ok"
    assert "at launch" in detail


def test_a_user_level_block_for_this_group_is_ok(home):
    target = engine_targets()["claude"]
    target.memory_file.parent.mkdir(parents=True, exist_ok=True)
    target.memory_file.write_text(render_block("common", "S"), encoding="utf-8")

    state, detail = _standards_detail(get_spec("claude"), "common")

    assert state == "ok"
    assert "user-level" in detail


def test_a_user_level_block_for_another_group_is_flagged(home):
    """用户级托管块只有一个 group 位，别的项目写进去后本项目的规范就失效了。"""
    target = engine_targets()["claude"]
    target.memory_file.parent.mkdir(parents=True, exist_ok=True)
    target.memory_file.write_text(render_block("work", "S"), encoding="utf-8")

    state, detail = _standards_detail(get_spec("claude"), "common")

    assert state == "warn"
    assert "work" in detail
    assert "common" in detail


def test_engines_without_a_channel_are_flagged(home):
    state, detail = _standards_detail(get_spec("antigravity"), "common")

    assert state == "warn"
    assert "no system-prompt channel" in detail
