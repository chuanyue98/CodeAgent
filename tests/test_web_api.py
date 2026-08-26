import json
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from core.web import server
from core.web.routers import tasks as tasks_router
from core.web.server import app


@pytest.fixture
def mock_env(tmp_path, monkeypatch):
    root_dir = tmp_path
    config_path = root_dir / "config.json"
    skills_root = root_dir / "skills"
    prompts_root = root_dir / "prompt"
    hooks_root = root_dir / "hooks"
    plugins_root = root_dir / "plugins"
    tasks_root = root_dir / "tasks"

    skills_root.mkdir()
    prompts_root.mkdir()
    hooks_root.mkdir()
    plugins_root.mkdir()
    tasks_root.mkdir()

    config = {
        "default_mode": "local",
        "proxy": {"host": "127.0.0.1", "port": 1087},
        "project_registry": [],
        "groups": {"common": {"skills": [], "prompts": [], "hooks": [], "plugins": []}},
        "hooks": {"project_hooks": {"common": ["base/test-hook"]}},
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    # Set environment variables for the new routers
    monkeypatch.setenv("CA_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("CA_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CA_SKILLS_ROOT", str(skills_root))
    monkeypatch.setenv("CA_PROMPTS_ROOT", str(prompts_root))
    monkeypatch.setenv("CA_HOOKS_ROOT", str(hooks_root))
    monkeypatch.setenv("CA_PLUGINS_ROOT", str(plugins_root))
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks_root))

    monkeypatch.setattr(server, "CONFIG_PATH", config_path)

    return root_dir


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_agent_gateway_settings_support_config_and_environment(monkeypatch):
    config = {
        "agent_gateway": {
            "enabled": False,
            "legacy_fallback": False,
            "providers": {"codebuddy": False, "codex": True},
        }
    }
    monkeypatch.setenv("CA_AGENT_GATEWAY_ENABLED", "1")
    monkeypatch.setenv("CA_AGENT_PROVIDER_CODEX", "false")

    settings = server.get_agent_gateway_settings(config)

    assert settings["enabled"] is True
    assert settings["legacyFallback"] is False
    assert settings["providers"] == {
        "codex": False,
        "claude": True,
        "opencode": True,
        "codebuddy": False,
    }


@pytest.mark.asyncio
async def test_api_root_without_built_frontend():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    if server.FRONTEND_DIST.exists():
        assert "text/html" in response.headers["content-type"]
    else:
        assert response.json()["ui"] == "http://127.0.0.1:5173"


@pytest.mark.asyncio
async def test_get_hooks(mock_env):
    # Setup a mock hook with correct metadata.json name
    hook_dir = mock_env / "hooks" / "base" / "test-hook"
    hook_dir.mkdir(parents=True)
    (hook_dir / "metadata.json").write_text(
        json.dumps(
            {"name": "Test Hook", "event": "pre-commit", "description": "A test hook"}
        )
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/hooks")

    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert any(h["id"] == "base/test-hook" for h in data)
    assert any(h["id"] == "base/test-hook" and h["isActive"] is True for h in data)


@pytest.mark.asyncio
async def test_list_tasks(mock_env, tmp_path):
    tasks_root = tmp_path / "tasks"
    tasks_root.mkdir(exist_ok=True)
    (tasks_root / "refactor.md").write_text(
        "# Refactor Task\nImprove code readability.", encoding="utf-8"
    )
    (tasks_root / "upgrade.md").write_text(
        "# Upgrade\n## 阶段 1\n**目标**: 升级依赖\n**状态**: 已完成\n",
        encoding="utf-8",
    )
    import os

    os.environ["CA_TASKS_ROOT"] = str(tasks_root)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/tasks")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = [t["name"] for t in data]
    assert "refactor" in names
    assert "upgrade" in names

    upgrade = next(t for t in data if t["name"] == "upgrade")
    assert upgrade["hasStages"] is True
    assert upgrade["stages"][0]["status"] == "已完成"


@pytest.mark.asyncio
async def test_run_task_uses_registered_group_and_atomic_overlap(mock_env, monkeypatch):
    workspace = mock_env / "workspace"
    workspace.mkdir()
    config_path = mock_env / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["project_registry"] = [{"path": str(workspace), "group": "work"}]
    config_path.write_text(json.dumps(config), encoding="utf-8")
    (mock_env / "tasks" / "review.md").write_text("# Review\n", encoding="utf-8")
    calls = []

    class FakeRunner:
        def run_task(self, name, engine, group, **kwargs):
            calls.append((name, engine, group, kwargs))
            return SimpleNamespace(
                task_id="review_1",
                engine=engine,
                pid=1,
                status="running",
                log_path="/tmp/review.log",
                start_time=0,
                session_id=None,
                workspace=str(workspace),
            )

    monkeypatch.setattr(tasks_router, "_runner", FakeRunner())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/tasks/review/run",
            json={
                "engine": "codex",
                "group": "common",
                "workspace": str(workspace),
            },
        )

    assert response.status_code == 200
    assert calls[0][2] == "work"
    assert calls[0][3]["prevent_overlap"] is True


@pytest.mark.asyncio
async def test_update_task_route(mock_env):
    (mock_env / "tasks" / "review.md").write_text("# Old\nold body", encoding="utf-8")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.put("/api/tasks/review", json={"content": "# New\nnew body"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New"
    assert "new body" in data["content"]
    assert (mock_env / "tasks" / "review.md").read_text(
        encoding="utf-8"
    ) == "# New\nnew body"


@pytest.mark.asyncio
async def test_update_task_route_404_for_missing(mock_env):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.put("/api/tasks/missing", json={"content": "# x\n"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_route(mock_env):
    (mock_env / "tasks" / "review.md").write_text("# Review\n", encoding="utf-8")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.delete("/api/tasks/review")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "name": "review"}
    assert not (mock_env / "tasks" / "review.md").exists()


@pytest.mark.asyncio
async def test_delete_task_route_409_when_active(mock_env, monkeypatch):
    (mock_env / "tasks" / "review.md").write_text("# Review\n", encoding="utf-8")

    class FakeRunner:
        def has_active_task(self, name, workspace=None):
            return True

    monkeypatch.setattr(tasks_router, "_runner", FakeRunner())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.delete("/api/tasks/review")
    assert resp.status_code == 409
    # File must still exist — the active-run guard blocks deletion.
    assert (mock_env / "tasks" / "review.md").exists()


@pytest.mark.asyncio
async def test_list_task_runs_route_queries_history_by_task_name(mock_env, monkeypatch):
    """The route asks the store for one task's history rather than filtering
    the in-memory map, which is what lets a finished run outlive the process
    that produced it."""
    from core.services.runner_service import TaskRunStatus

    calls = {}

    class FakeRunner:
        def list_history(self, *, task_name=None, limit=50):
            calls["task_name"] = task_name
            calls["limit"] = limit
            return [
                TaskRunStatus(
                    task_id="review_1",
                    engine="codex",
                    pid=1,
                    status="completed",
                    log_path="/tmp/a.log",
                    start_time=100,
                    end_time=200,
                    exit_code=0,
                    task_name="review",
                )
            ]

    monkeypatch.setattr(tasks_router, "_runner", FakeRunner())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get("/api/tasks/review/runs")

    assert resp.status_code == 200
    assert calls == {"task_name": "review", "limit": 50}
    data = resp.json()
    assert len(data) == 1
    assert data[0]["task_id"] == "review_1"
    assert data[0]["exit_code"] == 0
    assert data[0]["end_time"] == 200


@pytest.mark.asyncio
async def test_list_skills_with_frontmatter(mock_env):
    skill_dir = mock_env / "skills" / "base" / "fancy-skill"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\ndescription: Fancy description\n---\nBody content", encoding="utf-8"
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/skills")

    assert response.status_code == 200
    data = response.json()
    assert data["base"][0]["description"] == "Fancy description"
    assert "Body content" in data["base"][0]["readme"]


@pytest.mark.asyncio
async def test_list_prompts(mock_env):
    prompt_dir = mock_env / "prompt" / "coding"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "python.md").write_text("Python rules", encoding="utf-8")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/prompts")

    assert response.status_code == 200
    data = response.json()
    assert any(p["id"] == "coding" for p in data)
    assert "Python rules" in data[0]["readme"]


@pytest.mark.asyncio
async def test_projects_api_crud(mock_env):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Add
        resp = await ac.post("/api/projects", json={"path": "/p1", "group": "g1"})
        assert resp.status_code == 200

        # List
        resp = await ac.get("/api/projects")
        projects = resp.json()
        assert any(p["path"] == "/p1" for p in projects)
        assert next(p for p in projects if p["path"] == "/p1")["available"] is False

        # Delete
        resp = await ac.delete("/api/projects", params={"path": "/p1"})
        assert resp.status_code == 200
        new_projects = resp.json()["registry"]
        assert not any(p["path"] == "/p1" for p in new_projects)


@pytest.mark.asyncio
async def test_projects_api_validation_errors(mock_env):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Missing path
        resp = await ac.post("/api/projects", json={"group": "g1"})
        assert resp.status_code == 422

        # Missing group
        resp = await ac.post("/api/projects", json={"path": "/p1"})
        assert resp.status_code == 422

        # Empty path
        resp = await ac.post("/api/projects", json={"path": "", "group": "g1"})
        assert resp.status_code == 422

        # Whitespace-only values
        resp = await ac.post("/api/projects", json={"path": "   ", "group": "g1"})
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_projects_api_marks_existing_directories_available(mock_env):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/projects", json={"path": str(mock_env), "group": "common"}
        )
        assert resp.status_code == 200

        resp = await ac.get("/api/projects")

    project = next(item for item in resp.json() if item["path"] == str(mock_env))
    assert project["available"] is True


@pytest.mark.asyncio
async def test_groups_api_crud(mock_env):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Update
        group_data = {"skills": ["s1"], "prompts": ["p1"]}
        resp = await ac.post("/api/groups/new-group", json=group_data)
        assert resp.status_code == 200

        # List
        resp = await ac.get("/api/groups")
        assert "new-group" in resp.json()

        # Delete
        resp = await ac.delete("/api/groups/new-group")
        assert resp.status_code == 200
        groups = resp.json()["groups"]
        assert "new-group" not in groups

        resp = await ac.delete("/api/groups/missing-group")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_config_api(mock_env):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Get
        resp = await ac.get("/api/config")
        assert resp.status_code == 200
        assert resp.json()["default_mode"] == "local"

        # Update
        new_config = resp.json()
        new_config["default_mode"] = "remote"
        resp = await ac.post("/api/config", json=new_config)
        assert resp.status_code == 200

        # Verify
        resp = await ac.get("/api/config")
        assert resp.json()["default_mode"] == "remote"


@pytest.mark.asyncio
async def test_config_api_rejects_blank_project_rows(mock_env):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/config",
            json={
                "project_registry": [{"path": "  ", "group": "common"}],
                "groups": {},
            },
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_malformed_config_returns_server_error(mock_env):
    config_path = mock_env / "config.json"
    config_path.write_text("{ malformed", encoding="utf-8")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get("/api/config")

    assert resp.status_code == 200
    assert "Failed to parse config.json" in resp.json()["warnings"][0]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        update_resp = await ac.post("/api/config", json={"replacement": True})

    assert update_resp.status_code == 500
    assert config_path.read_text(encoding="utf-8") == "{ malformed"


def test_initialize_default_groups_logic(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(server, "CONFIG_PATH", config_path)
    monkeypatch.setenv("CA_SKILLS_ROOT", str(tmp_path / "skills"))
    monkeypatch.setenv("CA_PROMPTS_ROOT", str(tmp_path / "prompt"))
    monkeypatch.setenv("CA_PLUGINS_ROOT", str(tmp_path / "plugins"))
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompt").mkdir()
    (tmp_path / "hooks").mkdir()
    (tmp_path / "plugins").mkdir()

    server.initialize_default_groups()

    with open(config_path) as f:
        config = json.load(f)
        assert "groups" in config
        assert "common" in config["groups"]


@pytest.mark.asyncio
async def test_server_lifespan_cleanup_exceptions(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    import core.web.server as server_mod

    # Mock initialize_default_groups and scheduler_tick_loop to avoid real setup
    monkeypatch.setattr(server_mod, "initialize_default_groups", MagicMock())
    monkeypatch.setattr(server_mod, "scheduler_tick_loop", AsyncMock())

    mock_chat_runner = MagicMock()
    # Force one of them to raise an Exception to test independent try/except
    mock_chat_runner.kill_all.side_effect = Exception("chat cleanup failed")

    mock_tasks_runner = MagicMock()

    # Patch the imported runner modules inside lifespan context
    import core.web.routers.chat
    import core.web.routers.tasks

    monkeypatch.setattr(core.web.routers.chat, "_runner", mock_chat_runner)
    monkeypatch.setattr(core.web.routers.tasks, "_runner", mock_tasks_runner)

    dummy_app = MagicMock()
    async with server_mod.lifespan(dummy_app):
        pass

    # Verify both kill_all were called despite the exception in chat_runner.kill_all()
    mock_chat_runner.kill_all.assert_called_once()
    mock_tasks_runner.kill_all.assert_called_once()
