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


def test_rejects_invalid_requested_path(tmp_path, monkeypatch):
    """A path the OS itself refuses to resolve (embedded null byte, etc.)
    must map to the "invalid" error, not fall through to the "missing
    directory" one. Whether a given string actually triggers that at the
    OS level is platform- and Python-version-dependent (e.g. an embedded
    null byte raises on POSIX but pathlib silently tolerates it on
    Windows), so the failure is injected directly instead of relying on
    a string that happens to trip it on whatever machine runs this."""
    config_service = ConfigService(tmp_path / "config.json")

    class _UnresolvablePath:
        def __init__(self, *_args, **_kwargs):
            pass

        def expanduser(self):
            return self

        def resolve(self):
            raise ValueError("embedded null byte")

    monkeypatch.setattr("core.services.workspace_service.Path", _UnresolvablePath)

    try:
        resolve_registered_workspace(config_service, "\0invalid")
    except WorkspaceResolutionError as exc:
        assert str(exc) == "Workspace path is invalid"
    else:
        raise AssertionError("invalid workspace path was accepted")
