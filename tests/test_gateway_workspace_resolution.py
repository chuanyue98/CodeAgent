"""Starting an agent inside a registered project's subdirectory.

The gateway used to require the requested workspace to equal a registry entry
exactly, so a subdirectory of a registered project could not host a session at
all. That also kept ``core.project_groups.resolve_project_group`` -- which
resolves a project's group by longest prefix -- unreachable from the Web UI:
no subdirectory ever got far enough to need its group worked out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.services.agent_gateway import AgentGateway, AgentGatewayError


class _StubConfigService:
    def __init__(self, registry: list[dict]):
        self._registry = registry

    def get_config(self):
        return {"project_registry": self._registry}, []


def _resolve(tmp_path: Path, registry_paths: list[str], requested: Path):
    gateway = AgentGateway.__new__(AgentGateway)
    gateway._config_service = _StubConfigService(  # type: ignore[attr-defined]
        [{"path": p} for p in registry_paths]
    )
    return gateway._registered_workspace(str(requested))


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "demo" / "src" / "deep").mkdir(parents=True)
    (tmp_path / "demo-old").mkdir()
    return tmp_path


def test_an_exactly_registered_path_still_works(repo):
    root = repo / "demo"

    cwd, identity = _resolve(repo, [str(root)], root)

    assert Path(cwd) == root.resolve()
    assert identity == str(root)


def test_a_subdirectory_of_a_registered_project_is_allowed(repo):
    root = repo / "demo"
    sub = root / "src" / "deep"

    cwd, identity = _resolve(repo, [str(root)], sub)

    assert Path(cwd) == sub.resolve()
    # The identity stays the registered path: GET /api/projects returns that,
    # and the frontend matches a session against it.
    assert identity == str(root)


def test_the_deepest_registered_ancestor_wins(repo):
    root = repo / "demo"
    mid = root / "src"
    sub = mid / "deep"

    _cwd, identity = _resolve(repo, [str(root), str(mid)], sub)

    assert identity == str(mid)


def test_a_sibling_with_a_shared_prefix_is_not_an_ancestor(repo):
    # /work/demo-old must not match a rule of /work/demo, which is what a
    # string-prefix test would do.
    with pytest.raises(AgentGatewayError) as excinfo:
        _resolve(repo, [str(repo / "demo")], repo / "demo-old")

    assert excinfo.value.code == "workspace_not_registered"


def test_an_unregistered_tree_is_still_refused(repo):
    (repo / "elsewhere").mkdir()

    with pytest.raises(AgentGatewayError) as excinfo:
        _resolve(repo, [str(repo / "demo")], repo / "elsewhere")

    assert excinfo.value.code == "workspace_not_registered"


def test_a_path_that_is_not_a_directory_is_refused_before_the_registry(repo):
    with pytest.raises(AgentGatewayError) as excinfo:
        _resolve(repo, [str(repo / "demo")], repo / "demo" / "nope")

    assert excinfo.value.code == "workspace_unavailable"


def test_a_malformed_registry_entry_is_skipped_not_fatal(repo):
    root = repo / "demo"
    gateway = AgentGateway.__new__(AgentGateway)
    gateway._config_service = _StubConfigService(  # type: ignore[attr-defined]
        ["not-a-dict", {"path": 42}, {"path": str(root)}]  # type: ignore[list-item]
    )

    _cwd, identity = gateway._registered_workspace(str(root / "src"))

    assert identity == str(root)
