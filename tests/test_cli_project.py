"""``ca project add / remove / list`` 的 CLI 测试。"""

from unittest.mock import patch

import pytest

import ca_launcher


def _run(monkeypatch, *argv, config=None):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", *argv])
    if config is not None:
        monkeypatch.setattr("core.cli.helpers.load_config", lambda: config)
    return ca_launcher.main()


class FakeConfigService:
    def __init__(self, registry=None):
        self.registry = list(registry or [])
        self.added = []
        self.deleted = []

    def add_project(self, path, group):
        self.added.append((path, group))
        self.registry.append({"path": path, "group": group})
        return self.registry

    def delete_project(self, path):
        self.deleted.append(path)
        self.registry = [item for item in self.registry if item["path"] != path]
        return self.registry

    def get_config(self):
        return {"project_registry": self.registry}, []


@pytest.fixture
def config_service():
    fake = FakeConfigService()
    with patch("core.cli.commands.project.ConfigService", lambda path: fake):
        yield fake


# ── ca project add ───────────────────────────────────────────────────────────


def test_add_registers_a_directory_into_a_group(monkeypatch, capsys, tmp_path, config_service):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    config_service.registry = [{"path": "/existing", "group": "common"}]

    _run(
        monkeypatch, "project", "add", str(project_dir), "--group", "work",
        config={"groups": {"work": {}}},
    )

    assert config_service.added == [(str(project_dir), "work")]
    out = capsys.readouterr().out
    assert "[OK] Registered" in out and "group 'work'" in out
    assert "project_registry now has 2 entries." in out


def test_add_warns_when_the_group_does_not_exist(monkeypatch, capsys, tmp_path, config_service):
    _run(
        monkeypatch, "project", "add", str(tmp_path), "--group", "ghost",
        config={"groups": {}},
    )
    assert "Group 'ghost' doesn't exist" in capsys.readouterr().out
    # Registration still happens — the warning is advisory.
    assert config_service.added == [(str(tmp_path), "ghost")]


def test_add_rejects_a_path_that_is_not_a_directory(monkeypatch, capsys, tmp_path, config_service):
    missing = tmp_path / "nope"
    with pytest.raises(SystemExit) as excinfo:
        _run(monkeypatch, "project", "add", str(missing), config={"groups": {}})
    assert excinfo.value.code == 1
    assert "[X] Not a directory" in capsys.readouterr().out
    assert config_service.added == []


# ── ca project remove ────────────────────────────────────────────────────────


def test_remove_deletes_a_registered_project(monkeypatch, capsys, tmp_path, config_service):
    config_service.registry = [{"path": str(tmp_path), "group": "work"}]
    _run(monkeypatch, "project", "remove", str(tmp_path), config={})
    assert "[OK] Removed" in capsys.readouterr().out
    assert config_service.deleted == [str(tmp_path)]


def test_remove_missing_path_exits(monkeypatch, capsys, tmp_path, config_service):
    with pytest.raises(SystemExit) as excinfo:
        _run(monkeypatch, "project", "remove", str(tmp_path), config={})
    assert excinfo.value.code == 1
    assert "was not found in project_registry." in capsys.readouterr().out


# ── ca project list ──────────────────────────────────────────────────────────


def test_list_empty_registry(monkeypatch, capsys):
    _run(monkeypatch, "project", "list", config={"project_registry": []})
    assert "No projects registered." in capsys.readouterr().out


def test_list_marks_missing_directories(monkeypatch, capsys, tmp_path):
    existing = tmp_path / "here"
    existing.mkdir()
    config = {
        "project_registry": [
            {"path": str(existing), "group": "work"},
            {"path": "/definitely/gone", "group": "common"},
        ]
    }
    _run(monkeypatch, "project", "list", config=config)
    out = capsys.readouterr().out
    assert f"v  {existing}  (group: work)" in out
    assert "x (missing)  /definitely/gone  (group: common)" in out
