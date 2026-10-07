"""引擎注册表里的「挂载了什么」和各引擎启动器实际做的事保持一致。

``EngineSpec.mounts`` 是手写的声明，Web UI 拿它在每个技能、Hook、插件旁边标出
会挂到哪些引擎。启动器改了却没人回来改这张表，界面就会说错话，所以这里逐个
引擎去读启动器的源码：声明了某类就必须能找到挂它的调用，没声明就不能有。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.engine_registry import ENGINES, MOUNTABLE_KINDS
from core.resource_locator import CODE_ROOT
from core.web.routers import system

#: 每个引擎的启动器里，挂某一类资源时会出现的调用。任何一个出现就算挂了。
MARKERS: dict[str, dict[str, tuple[str, ...]]] = {
    "skills": {
        "claude": ("ensure_plugin_dir",),
        "opencode": ("ensure_skills_link",),
        "codex": ("ensure_skills_link",),
        "codebuddy": ("ensure_plugin_dir",),
        "antigravity": ("ensure_plugin_bundle",),
    },
    "hooks": {
        "claude": ("plugin_hooks_config",),
        "opencode": ("ensure_hooks_bridge",),
        "codex": ("inject_hooks_to_settings",),
        "codebuddy": ("plugin_hooks_config",),
        "antigravity": ("inject_hooks_to_settings", "ensure_hooks_bridge"),
    },
    "plugins": {
        "claude": ("resolve_group_plugin_dirs",),
        "opencode": ("get_plugins_to_mount",),
        "codex": ("get_plugins_to_mount", "ensure_plugins_available"),
        "codebuddy": ("plugin_dir_env",),
        "antigravity": ("get_plugins_to_mount", "plugin_dir_env"),
    },
}


def _launcher_source(engine: str) -> str:
    return (CODE_ROOT / "engines" / ENGINES[engine].launch_script).read_text(
        encoding="utf-8"
    )


def test_every_engine_has_markers_for_every_kind():
    for kind in MOUNTABLE_KINDS:
        assert set(MARKERS[kind]) == set(ENGINES), f"{kind}: engine list drifted"


@pytest.mark.parametrize("engine", sorted(ENGINES))
@pytest.mark.parametrize("kind", MOUNTABLE_KINDS)
def test_declared_mounts_match_what_the_launcher_does(engine: str, kind: str):
    source = _launcher_source(engine)
    attaches = any(marker in source for marker in MARKERS[kind][engine])
    declared = kind in ENGINES[engine].mounts

    assert declared == attaches, (
        f"{engine} {'declares' if declared else 'does not declare'} {kind}, but its "
        f"launcher {'does not attach' if declared else 'attaches'} them; "
        "update EngineSpec.mounts in core/engine_registry.py (or the markers here)"
    )


def test_mounts_only_use_known_kinds():
    for spec in ENGINES.values():
        assert spec.mounts <= set(MOUNTABLE_KINDS), spec.name


# ── GET /api/system/engines ──────────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(system.router)
    return TestClient(app)


def test_endpoint_lists_every_engine_with_its_mounts(client: TestClient):
    body = client.get("/api/system/engines").json()

    by_id = {engine["id"]: engine for engine in body["engines"]}
    assert set(by_id) == set(ENGINES)
    assert by_id["claude"]["mounts"] == ["skills", "hooks", "plugins"]
    assert by_id["codebuddy"]["mounts"] == ["skills", "hooks", "plugins"]
    assert by_id["antigravity"]["mounts"] == ["skills"]
    assert by_id["claude"]["name"] == ENGINES["claude"].display_name


def test_endpoint_reports_mounts_in_the_registry_kind_order(client: TestClient):
    for engine in client.get("/api/system/engines").json()["engines"]:
        order = [kind for kind in MOUNTABLE_KINDS if kind in engine["mounts"]]
        assert engine["mounts"] == order
