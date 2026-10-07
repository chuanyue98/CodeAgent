"""``.agents/skills`` 里的技能挂给不原生读取它的引擎（Claude、CodeBuddy）。"""

from __future__ import annotations

from pathlib import Path

import pytest

import engines.start_claude_code as claude_mod
import engines.start_codebuddy as codebuddy_mod
import engines.start_codex as codex_mod
import engines.start_opencode as opencode_mod


def _skill(root: Path, name: str) -> Path:
    path = root / name
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    return path


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    monkeypatch.setenv("USERPROFILE", str(path))
    monkeypatch.delenv("CODEBUDDY_CONFIG_DIR", raising=False)
    return path


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "work" / "repo"
    (path / ".git").mkdir(parents=True)
    monkeypatch.chdir(path)
    return path


def _sources(engine_cls, monkeypatch, group=()):
    monkeypatch.setattr(
        engine_cls, "_resolve_group_skill_sources", lambda self: list(group)
    )
    return {name: src for name, src in engine_cls().resolve_skill_sources()}


def test_project_and_user_agents_skills_reach_claude(home, project, monkeypatch):
    _skill(project / ".agents" / "skills", "from-project")
    _skill(home / ".agents" / "skills", "from-user")

    sources = _sources(claude_mod.ClaudeEngine, monkeypatch)

    assert set(sources) == {"from-project", "from-user"}


def test_a_group_skill_wins_over_an_agents_skill_of_the_same_name(
    tmp_path, home, project, monkeypatch
):
    _skill(project / ".agents" / "skills", "review")
    group_src = _skill(tmp_path / "group", "review")

    sources = _sources(
        claude_mod.ClaudeEngine, monkeypatch, group=[("review", group_src)]
    )

    assert sources == {"review": group_src}


def test_a_skill_the_engine_already_has_is_not_mounted_twice(
    home, project, monkeypatch
):
    """不少安装器把同一份技能同时拷进 ~/.agents/skills 和 ~/.claude/skills。"""
    _skill(home / ".agents" / "skills", "hyperframes")
    _skill(home / ".claude" / "skills", "hyperframes")
    _skill(home / ".agents" / "skills", "only-in-agents")

    assert set(_sources(claude_mod.ClaudeEngine, monkeypatch)) == {"only-in-agents"}


def test_codebuddy_skips_skills_in_its_own_home(home, project, monkeypatch):
    _skill(home / ".agents" / "skills", "shared")
    _skill(home / ".codebuddy" / "skills", "shared")
    _skill(project / ".agents" / "skills", "local")

    assert set(_sources(codebuddy_mod.CodeBuddyEngine, monkeypatch)) == {"local"}


def test_the_project_copy_wins_over_the_users(home, project, monkeypatch):
    local = _skill(project / ".agents" / "skills", "lint")
    _skill(home / ".agents" / "skills", "lint")

    assert _sources(claude_mod.ClaudeEngine, monkeypatch) == {"lint": local.resolve()}


def test_the_search_stops_at_the_git_root(home, project, monkeypatch):
    sub = project / "packages" / "app"
    sub.mkdir(parents=True)
    _skill(project / ".agents" / "skills", "repo-level")
    _skill(project.parent / ".agents" / "skills", "outside-the-repo")
    monkeypatch.chdir(sub)

    assert set(_sources(claude_mod.ClaudeEngine, monkeypatch)) == {"repo-level"}


def test_entries_without_skill_md_are_ignored(home, project, monkeypatch):
    (project / ".agents" / "skills" / "notes").mkdir(parents=True)

    assert _sources(claude_mod.ClaudeEngine, monkeypatch) == {}


@pytest.mark.parametrize(
    "engine_cls", [codex_mod.CodexEngine, opencode_mod.OpenCodeEngine]
)
def test_engines_that_read_agents_skills_natively_get_nothing_extra(
    engine_cls, home, project, monkeypatch
):
    _skill(project / ".agents" / "skills", "from-project")
    _skill(home / ".agents" / "skills", "from-user")

    assert _sources(engine_cls, monkeypatch) == {}
