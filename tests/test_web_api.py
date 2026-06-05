import pytest
import json
from httpx import ASGITransport, AsyncClient
from core.web import server
from core.web.server import app, create_app


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


@pytest.mark.asyncio
async def test_api_root_without_built_frontend(tmp_path):
    api_only_app = create_app(frontend_dist=tmp_path / "missing-dist")
    async with AsyncClient(
        transport=ASGITransport(app=api_only_app), base_url="http://test"
    ) as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    assert response.json()["ui"] == "http://127.0.0.1:5173"


@pytest.mark.asyncio
async def test_spa_root_with_built_frontend(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><div id='root'></div>")

    spa_app = create_app(frontend_dist=dist)
    async with AsyncClient(
        transport=ASGITransport(app=spa_app), base_url="http://test"
    ) as ac:
        response = await ac.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "root" in response.text


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
async def test_projects_api_rejects_invalid_payload(mock_env):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post("/api/projects", json={"path": "/missing-group"})

    assert resp.status_code == 422


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
async def test_delete_missing_group_returns_404(mock_env):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
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

    with open(config_path, "r") as f:
        config = json.load(f)
        assert "groups" in config
        assert "common" in config["groups"]
