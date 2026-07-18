from core.services.config_service import ConfigService
from core.services.workspace_service import (
    WorkspaceResolutionError,
    resolve_registered_workspace,
)


def test_skips_invalid_registry_paths(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_service = ConfigService(tmp_path / "config.json")
    config_service.update_config(
        {
            "project_registry": [
                {"path": "\0invalid", "group": "broken"},
                {"path": str(workspace), "group": "work"},
            ]
        }
    )

    resolved = resolve_registered_workspace(config_service, str(workspace))

    assert resolved.path == str(workspace.resolve())
    assert resolved.group == "work"


def test_rejects_invalid_requested_path(tmp_path):
    config_service = ConfigService(tmp_path / "config.json")

    try:
        resolve_registered_workspace(config_service, "\0invalid")
    except WorkspaceResolutionError as exc:
        assert str(exc) == "Workspace path is invalid"
    else:
        raise AssertionError("invalid workspace path was accepted")
