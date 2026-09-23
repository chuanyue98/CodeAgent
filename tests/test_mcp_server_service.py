"""Tests for the MCP server service (core/services/mcp_server_service.py)."""

from __future__ import annotations

import asyncio
import json

import pytest

from core.delegation_depth import DEPTH_ENV
from core.services.mcp_server_service import (
    build_delegation_server,
    build_server,
    discover_skills,
)


def _text(result) -> str:
    """FastMCP 1.28 的 call_tool 返回 (content_blocks, structured),统一取第一块文本。"""
    blocks = result[0] if isinstance(result, tuple) else result
    return blocks[0].text if blocks else ""


# 与 core/skill_scanner.SkillScanner 的发现逻辑同构:skills/<category>/<skill>/SKILL.md
SKILL_MD_TEMPLATE = """\
---
name: {name}
description: {description}
---

# {name}

Body of {name}.
"""


@pytest.fixture
def skills_root(tmp_path):
    root = tmp_path / "skills"
    for category, skills in (("base", ["alpha", "beta"]), ("extra", ["gamma"])):
        for skill in skills:
            d = root / category / skill
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(
                SKILL_MD_TEMPLATE.format(name=skill, description=f"desc of {skill}"),
                encoding="utf-8",
            )
    return root


def test_discover_skills_lists_all(skills_root):
    skills = discover_skills(skills_root)
    names = {s["name"] for s in skills}
    assert names == {"alpha", "beta", "gamma"}
    by_name = {s["name"]: s for s in skills}
    assert by_name["alpha"]["category"] == "base"
    assert by_name["alpha"]["description"] == "desc of alpha"
    assert by_name["gamma"]["category"] == "extra"


def test_discover_skills_missing_root(tmp_path):
    assert discover_skills(tmp_path / "nope") == []


def test_discover_skills_group_filter(skills_root):
    config = {"groups": {"work": {"skills": ["base/alpha", "base/beta"]}}}
    names = {s["name"] for s in discover_skills(skills_root, config, group="work")}
    assert names == {"alpha", "beta"}


def test_discover_skills_unknown_group(skills_root):
    config = {"groups": {"work": {"skills": ["base/alpha"]}}}
    assert discover_skills(skills_root, config, group="nope") == []


def test_discover_skills_group_without_config(skills_root):
    # 指定了组但没给 config,视为无资产可挂载(而非崩溃)
    assert discover_skills(skills_root, None, group="work") == []


def test_discover_skills_bad_frontmatter(tmp_path):
    root = tmp_path / "skills"
    d = root / "base" / "plain"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("# plain\n\nno frontmatter here\n", encoding="utf-8")
    skills = discover_skills(root)
    assert len(skills) == 1
    assert skills[0]["name"] == "plain"
    assert skills[0]["description"].startswith("plain")


def test_build_server_exposes_expected_assets(skills_root):
    server = build_server(config=None, group=None, skills_root=skills_root)
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {"skill_list", "skill_read"} <= names
    templates = asyncio.run(server.list_resource_templates())
    uris = {t.uriTemplate for t in templates}
    assert "ca://skill/{name}" in uris


def test_skill_list_json_payload(skills_root):
    server = build_server(config=None, group=None, skills_root=skills_root)
    result = asyncio.run(server.call_tool("skill_list", {}))
    payload = json.loads(_text(result))
    assert {s["name"] for s in payload} == {"alpha", "beta", "gamma"}


def test_skill_read_content(skills_root):
    server = build_server(config=None, group=None, skills_root=skills_root)
    found = asyncio.run(server.call_tool("skill_read", {"name": "alpha"}))
    assert "desc of alpha" in _text(found)
    missing = asyncio.run(server.call_tool("skill_read", {"name": "nope"}))
    assert "不存在" in _text(missing)


def test_group_bound_server(skills_root):
    config = {"groups": {"work": {"skills": ["base/alpha"]}}}
    server = build_server(config=config, group="work", skills_root=skills_root)
    result = asyncio.run(server.call_tool("skill_list", {}))
    names = {s["name"] for s in json.loads(_text(result))}
    assert names == {"alpha"}


def test_write_tools_hidden_by_default(skills_root):
    server = build_server(config=None, group=None, skills_root=skills_root)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {
        "skill_run",
        "task_run",
        "hook_fire",
        "ca_delegate",
        "ca_handoff_session",
    } & names == set()


def test_write_tools_visible_with_allow_write(skills_root, monkeypatch):
    monkeypatch.delenv(DEPTH_ENV)
    server = build_server(
        config=None, group=None, skills_root=skills_root, allow_write=True
    )
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {
        "skill_run",
        "task_run",
        "ca_delegate",
        "ca_delegate_wait",
        "ca_delegate_list",
        "ca_delegate_stop",
        "ca_handoff_session",
    } <= names
    assert "hook_fire" not in names  # 需要 trust_hooks


def test_hook_fire_requires_trust_hooks(skills_root):
    server = build_server(
        config=None,
        group=None,
        skills_root=skills_root,
        allow_write=True,
        trust_hooks=True,
    )
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert "hook_fire" in names


def test_skill_run_executes_script(skills_root):
    # 给 alpha 技能放一个可执行脚本
    script = skills_root / "base" / "alpha" / "scripts" / "run.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "import sys\nprint('hello from alpha', sys.argv[1:])\n",
        encoding="utf-8",
    )
    server = build_server(
        config=None, group=None, skills_root=skills_root, allow_write=True
    )
    result = asyncio.run(
        server.call_tool("skill_run", {"name": "alpha", "args": "--foo bar"})
    )
    out = _text(result)
    assert "exit=0" in out
    assert "hello from alpha" in out


def test_skill_run_rejects_path_traversal(skills_root):
    server = build_server(
        config=None, group=None, skills_root=skills_root, allow_write=True
    )
    result = asyncio.run(
        server.call_tool("skill_run", {"name": "alpha", "script": "../../etc/passwd"})
    )
    assert "越界" in _text(result)


def test_skill_run_missing_skill_returns_error(skills_root):
    server = build_server(
        config=None, group=None, skills_root=skills_root, allow_write=True
    )
    result = asyncio.run(server.call_tool("skill_run", {"name": "nope"}))
    assert "不存在" in _text(result)


def test_skill_run_falls_back_to_doc_without_script(skills_root):
    # alpha 没有 scripts,应回退为返回 SKILL.md 指引而非报错/执行
    server = build_server(
        config=None, group=None, skills_root=skills_root, allow_write=True
    )
    result = asyncio.run(server.call_tool("skill_run", {"name": "alpha"}))
    assert "操作指引" in _text(result)


def test_task_run_delegates_to_runner(skills_root, monkeypatch):
    class _FakeStatus:
        task_id = "t1"
        engine = "claude"
        status = "running"
        pid = 1234
        log_path = "/tmp/t1.log"

    class _FakeRunner:
        def __init__(self, root):
            self.root = root

        def run_task(self, task_name, engine, group="common"):
            assert task_name == "mytask" and engine == "claude"
            return _FakeStatus()

    monkeypatch.setattr("core.services.runner_service.TaskRunner", _FakeRunner)
    server = build_server(
        config=None, group=None, skills_root=skills_root, allow_write=True
    )
    result = asyncio.run(
        server.call_tool("task_run", {"task_name": "mytask", "engine": "claude"})
    )
    payload = json.loads(_text(result))
    assert payload["task_id"] == "t1" and payload["engine"] == "claude"


def test_hook_fire_rejects_bad_json(skills_root, tmp_path, monkeypatch):
    import core.services.mcp_server_service as mod

    # 指向临时 hooks 根,避免污染真实资源
    hooks_root = tmp_path / "hooks"
    hdir = hooks_root / "base" / "demo"
    hdir.mkdir(parents=True)
    (hdir / "hook.py").write_text("import sys\nprint('x')\n", encoding="utf-8")
    monkeypatch.setattr(mod, "get_bundled_resource_root", lambda: tmp_path)
    server = build_server(
        config=None, group=None, skills_root=skills_root, trust_hooks=True
    )
    result = asyncio.run(
        server.call_tool("hook_fire", {"hook_name": "demo", "event_json": "{bad"})
    )
    assert "合法 JSON" in _text(result)


def test_hook_fire_executes_and_returns_output(skills_root, tmp_path, monkeypatch):
    import core.services.mcp_server_service as mod

    hooks_root = tmp_path / "hooks"
    hdir = hooks_root / "base" / "demo"
    hdir.mkdir(parents=True)
    (hdir / "hook.py").write_text(
        "import sys\nprint('got:', sys.stdin.read().strip())\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "get_bundled_resource_root", lambda: tmp_path)
    server = build_server(
        config=None, group=None, skills_root=skills_root, trust_hooks=True
    )
    result = asyncio.run(
        server.call_tool("hook_fire", {"hook_name": "demo", "event_json": '{"a": 1}'})
    )
    out = _text(result)
    assert "exit=0" in out
    assert "got:" in out and '"a": 1' in out


def test_ca_delegate_starts_in_background_and_returns_run_id(
    skills_root, tmp_path, monkeypatch
):
    monkeypatch.delenv(DEPTH_ENV)
    started: dict = {}

    def fake_start(engine, instruction, **kwargs):
        started.update(engine=engine, instruction=instruction, **kwargs)
        return "codex-20260923-120000-abcdef"

    monkeypatch.setattr("core.services.delegation_runs.start_delegation", fake_start)
    server = build_server(
        config=None,
        group=None,
        skills_root=skills_root,
        allow_write=True,
        root_dir=tmp_path,
    )
    out = json.loads(
        _text(
            asyncio.run(
                server.call_tool(
                    "ca_delegate",
                    {"engine": "codex", "instruction": "review", "mode": "review"},
                )
            )
        )
    )
    assert out["run_id"] == "codex-20260923-120000-abcdef"
    assert started["mode"] == "review"
    assert started["workspace"] == tmp_path
    assert not (tmp_path / ".ca_task_logs").exists(), "不往用户项目里写审计日志"


def test_delegation_tools_hidden_at_depth_limit(skills_root, monkeypatch):
    """被委派出来的子引擎（深度已到上限）看不到任何委派工具。"""
    monkeypatch.setenv(DEPTH_ENV, "1")
    server = build_server(
        config=None, group=None, skills_root=skills_root, allow_write=True
    )
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert not {n for n in names if n.startswith("ca_delegate")}
    assert not asyncio.run(build_delegation_server().list_tools())


def test_delegation_server_exposes_only_delegation_tools(monkeypatch):
    monkeypatch.delenv(DEPTH_ENV)
    names = {t.name for t in asyncio.run(build_delegation_server().list_tools())}
    assert names == {
        "ca_delegate",
        "ca_delegate_wait",
        "ca_delegate_list",
        "ca_delegate_stop",
    }


def test_ca_handoff_session_tool(skills_root, tmp_path, monkeypatch):
    fake_handoff = {
        "status": "ready",
        "source_engine": "claude",
        "target_engine": "codex",
        "original_session_id": "s1",
        "new_session_id": "s2",
        "resume_command": "ca codex --resume s2",
        "reason": "rate limit",
        "message": "Continue with ca codex",
    }
    monkeypatch.setattr(
        "core.services.delegation_service.handoff_session",
        lambda **kwargs: fake_handoff,
    )
    server = build_server(
        config=None,
        group=None,
        skills_root=skills_root,
        allow_write=True,
        root_dir=tmp_path,
    )
    result = asyncio.run(
        server.call_tool(
            "ca_handoff_session",
            {"target_engine": "codex", "reason": "rate limit"},
        )
    )
    payload = json.loads(_text(result))
    assert payload["status"] == "ready"
    assert payload["target_engine"] == "codex"

    # Check audit log written
    audit_file = tmp_path / ".ca_task_logs" / "mcp_audit.log"
    assert audit_file.exists()
    assert "ca_handoff_session" in audit_file.read_text(encoding="utf-8")
