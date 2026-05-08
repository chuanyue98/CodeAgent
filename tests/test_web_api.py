import pytest
import json
from httpx import ASGITransport, AsyncClient
from core.web import server
from core.web.server import app


@pytest.fixture
def mock_env(tmp_path, monkeypatch):
    root_dir = tmp_path
    config_path = root_dir / "config.json"
    skills_root = root_dir / "skills"
    prompts_root = root_dir / "prompt"
    hooks_root = root_dir / "hooks"
    plugins_root = root_dir / "plugins"

    skills_root.mkdir()
    prompts_root.mkdir()
    hooks_root.mkdir()
    plugins_root.mkdir()

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

    # Also monkeypatch server globals for backward compatibility if needed
    monkeypatch.setattr(server, "ROOT_DIR", root_dir)
    monkeypatch.setattr(server, "CONFIG_PATH", config_path)
    monkeypatch.setattr(server, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(server, "PROMPTS_ROOT", prompts_root)
    monkeypatch.setattr(server, "HOOKS_ROOT", hooks_root)

    return root_dir


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
async def test_get_task_status(mock_env):
    plan_path = mock_env / "IMPLEMENTATION_PLAN.md"
    plan_content = """
# Plan
## 阶段 1: 基础
**目标**: 实现基础功能
**状态**: [完成]
## 阶段 2: 高级
**目标**: 实现高级功能
**状态**: 进行中
"""
    plan_path.write_text(plan_content, encoding="utf-8")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/task")

    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert len(data["tasks"]) == 2
    assert data["tasks"][0]["name"] == "阶段 1: 基础"
    assert data["tasks"][0]["status"] == "完成"


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

        # Delete
        resp = await ac.delete("/api/projects", params={"path": "/p1"})
        assert resp.status_code == 200
        new_projects = resp.json()["registry"]
        assert not any(p["path"] == "/p1" for p in new_projects)


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


def test_initialize_default_groups_logic(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(server, "CONFIG_PATH", config_path)
    monkeypatch.setattr(server, "SKILLS_ROOT", tmp_path / "skills")
    monkeypatch.setattr(server, "PROMPTS_ROOT", tmp_path / "prompt")
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompt").mkdir()
    (tmp_path / "hooks").mkdir()

    server.initialize_default_groups()

    with open(config_path, "r") as f:
        config = json.load(f)
        assert "groups" in config
        assert "common" in config["groups"]
