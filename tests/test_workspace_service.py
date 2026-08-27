import pytest

from core.services.config_service import ConfigService
from core.services.workspace_service import (
    WorkspaceNotRegisteredError,
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


# ─── A registry entry covers everything beneath it ────────────────────────
#
# This resolver used to compare for equality while `core.project_groups` and
# the agent gateway both matched the nearest enclosing rule. In a
# subdirectory of a registered project you could therefore start an agent
# session and get a resource group, but could not run a task or create a
# schedule -- the same config answered differently depending on which half of
# the app asked.


def _registry(tmp_path, entries):
    config_service = ConfigService(tmp_path / "config.json")
    config_service.update_config({"project_registry": entries})
    return config_service


def test_a_subdirectory_of_a_registered_project_resolves(tmp_path):
    project = tmp_path / "demo"
    nested = project / "packages" / "api"
    nested.mkdir(parents=True)
    config_service = _registry(tmp_path, [{"path": str(project), "group": "web"}])

    resolved = resolve_registered_workspace(config_service, str(nested))

    # The work runs in the subdirectory; the group comes from the rule above.
    assert resolved.path == str(nested.resolve())
    assert resolved.group == "web"


def test_the_nearest_enclosing_rule_wins(tmp_path):
    outer = tmp_path / "demo"
    inner = outer / "CodeAgent"
    deeper = inner / "core"
    deeper.mkdir(parents=True)
    config_service = _registry(
        tmp_path,
        [
            {"path": str(outer), "group": "web"},
            {"path": str(inner), "group": "codeagent"},
        ],
    )

    assert (
        resolve_registered_workspace(config_service, str(deeper)).group == "codeagent"
    )


def test_a_sibling_sharing_a_name_prefix_is_not_covered(tmp_path):
    registered = tmp_path / "demo"
    registered.mkdir()
    sibling = tmp_path / "demo-old"
    sibling.mkdir()
    config_service = _registry(tmp_path, [{"path": str(registered), "group": "web"}])

    # Ancestry, not string prefix: the sibling falls through to the default
    # group rather than inheriting the registered one.
    assert (
        resolve_registered_workspace(
            config_service, str(sibling), interactive=True
        ).group
        != "web"
    )


def test_an_unregistered_tree_is_usable_on_a_loopback_bind(tmp_path):
    """Requiring an entry here would protect nobody.

    A drive-by page is already refused by the Host and Origin checks, and
    another process running as this user can execute commands regardless of
    what ``cwd`` this endpoint accepts. Charging a setup step for it made
    working in a fresh directory fail the PTY handshake with a bare 403.
    """
    registered = tmp_path / "demo"
    registered.mkdir()
    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()
    config_service = _registry(tmp_path, [{"path": str(registered), "group": "web"}])

    resolved = resolve_registered_workspace(
        config_service, str(elsewhere), interactive=True
    )

    assert resolved.path == str(elsewhere.resolve())
    assert resolved.group == "common"


def test_an_unregistered_tree_is_refused_on_a_non_loopback_bind(tmp_path, monkeypatch):
    """Reachable from the network, the registry is a real boundary again."""
    monkeypatch.setenv("CA_UI_HOST", "0.0.0.0")
    registered = tmp_path / "demo"
    registered.mkdir()
    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()
    config_service = _registry(tmp_path, [{"path": str(registered), "group": "web"}])

    with pytest.raises(WorkspaceNotRegisteredError):
        resolve_registered_workspace(config_service, str(elsewhere), interactive=True)

    # A registered tree keeps working there.
    assert resolve_registered_workspace(config_service, str(registered)).group == "web"


def test_the_configured_default_group_is_used_for_unmatched_directories(tmp_path):
    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()
    config_service = ConfigService(tmp_path / "config.json")
    config_service.update_config({"project_registry": [], "default_group": "work"})

    assert (
        resolve_registered_workspace(
            config_service, str(elsewhere), interactive=True
        ).group
        == "work"
    )


def test_an_entry_without_a_group_does_not_shadow_an_enclosing_rule(tmp_path):
    """A groupless entry is malformed config, not a rule for "no resources"."""
    outer = tmp_path / "demo"
    inner = outer / "CodeAgent"
    inner.mkdir(parents=True)
    config_service = _registry(
        tmp_path,
        [
            {"path": str(outer), "group": "web"},
            {"path": str(inner), "group": ""},
        ],
    )

    assert resolve_registered_workspace(config_service, str(inner)).group == "web"


def test_unattended_work_still_requires_an_entry_on_loopback(tmp_path):
    """Removing a project is how you say "stop acting here on your own"."""
    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()
    config_service = _registry(tmp_path, [])

    with pytest.raises(WorkspaceNotRegisteredError):
        resolve_registered_workspace(config_service, str(elsewhere))
