"""Tests for the MCP server service (core/services/mcp_server_service.py)."""

from __future__ import annotations

import asyncio
import json

import pytest

from core.services.mcp_server_service import build_server, discover_skills


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
