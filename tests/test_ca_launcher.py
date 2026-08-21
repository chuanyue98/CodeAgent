import json
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

import ca_launcher


def _wait_for(predicate, timeout=2.0):
    """Polls until `predicate()` is truthy or `timeout` seconds elapse.

    run_ui_command() now opens the browser from a background thread (it
    waits for the API port to accept connections first -- see
    _wait_for_api_then_open_browser) instead of calling it inline, so
    tests can no longer assert on the browser-open mock immediately after
    run_ui_command() returns.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


@pytest.fixture
def mock_config(tmp_path):
    config = {
        "default_mode": "remote",
        "language": "en",
        "proxy": {"host": "1.2.3.4", "port": 8888},
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))
    return config_file


def test_load_config_default(tmp_path, monkeypatch):
    # Test loading when config.json does not exist
    monkeypatch.chdir(tmp_path)
    with patch("core.cli.helpers._project_root", return_value=tmp_path):
        config = ca_launcher.load_config()
        assert config["default_mode"] == "local"
        assert config["proxy"]["port"] == 1087


def test_load_config_custom(mock_config, monkeypatch):
    # Test loading custom config.json
    monkeypatch.chdir(mock_config.parent)
    with patch("core.cli.helpers._project_root", return_value=mock_config.parent):
        config = ca_launcher.load_config()
        assert config["default_mode"] == "remote"
        assert config["proxy"]["host"] == "1.2.3.4"
        assert config["proxy"]["port"] == 8888


def test_is_tcp_port_open():
    with patch("socket.create_connection") as mock_conn:
        # Success case
        mock_conn.return_value.__enter__.return_value = MagicMock()
        assert ca_launcher.is_tcp_port_open("localhost", 80) is True

        # Failure case
        mock_conn.side_effect = OSError()
        assert ca_launcher.is_tcp_port_open("localhost", 80) is False


def test_find_available_port():
    with patch("socket.socket") as mock_sock:
        mock_s = mock_sock.return_value.__enter__.return_value
        # First port taken (8524), second free (8525)
        mock_s.connect_ex.side_effect = [0, 1]
        assert ca_launcher.find_available_port(8524) == 8525


def test_build_proxy_env():
    config = {"proxy": {"host": "myproxy", "port": 3066}}
    with patch("core.cli.helpers.is_tcp_port_open", return_value=True):
        env, host, port, scheme = ca_launcher.build_proxy_env(config)
        assert host == "myproxy"
        assert port == 3066
        assert scheme == "socks5"
        assert env["HTTP_PROXY"] == "socks5://myproxy:3066"


def test_project_root_prefers_current_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    (workspace / "core").mkdir(parents=True)
    (workspace / "engines").mkdir()
    (workspace / "web" / "frontend").mkdir(parents=True)
    (workspace / "web" / "frontend" / "package.json").write_text("{}")
    (workspace / "pyproject.toml").write_text("[project]\nname='demo'\n")
    nested = workspace / "docs" / "guides"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    with patch("core.cli.helpers._installed_root", return_value=tmp_path / "installed"):
        assert ca_launcher._project_root() == workspace


def test_main_help(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "--help"])
    ca_launcher.main()
    captured = capsys.readouterr()
    assert "Usage:" in captured.out
    assert "CodeAgent: Professional AI Engineering Shell" in captured.out


def test_main_ui_command(monkeypatch):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "ui"])
    with patch("core.cli.ui.run_ui_command", return_value=0) as mock_ui:
        assert ca_launcher.main() == 0
        mock_ui.assert_called_once()


def test_run_ui_command_uses_existing_vite_server(capsys, monkeypatch):
    monkeypatch.setenv("CA_UI_DEV", "1")
    mock_open_browser = MagicMock()
    mock_uvicorn = MagicMock()
    mock_server = MagicMock(app=object())
    fake_modules = {
        "uvicorn": mock_uvicorn,
        "core.web.server": mock_server,
    }

    with patch.dict(sys.modules, fake_modules):
        with patch("core.cli.ui._frontend_source_exists", return_value=True):
            with patch("core.cli.ui._is_ui_dev_server_running", return_value=True):
                with patch("core.cli.ui._open_browser", mock_open_browser):
                    with patch("core.cli.helpers.is_tcp_port_open", return_value=True):
                        assert ca_launcher.run_ui_command() == 0
                        assert _wait_for(lambda: mock_open_browser.called)

    mock_open_browser.assert_called_once_with("http://127.0.0.1:5173")
    mock_uvicorn.run.assert_called_once_with(
        mock_server.app, host="127.0.0.1", port=8524, log_level="info"
    )
    captured = capsys.readouterr()
    assert "Detected Vite dev server" in captured.out


def test_run_ui_command_starts_vite_server_when_available(capsys, monkeypatch):
    monkeypatch.setenv("CA_UI_DEV", "1")
    mock_open_browser = MagicMock()
    mock_uvicorn = MagicMock()
    mock_server = MagicMock(app=object())
    fake_modules = {
        "uvicorn": mock_uvicorn,
        "core.web.server": mock_server,
    }

    with patch.dict(sys.modules, fake_modules):
        with patch("core.cli.ui._frontend_source_exists", return_value=True):
            with patch("core.cli.ui._is_ui_dev_server_running", return_value=False):
                with patch(
                    "core.cli.ui._start_ui_dev_server", return_value=True
                ) as mock_start:
                    with patch("core.cli.ui._open_browser", mock_open_browser):
                        with patch("core.cli.helpers.is_tcp_port_open", return_value=True):
                            assert ca_launcher.run_ui_command() == 0
                            assert _wait_for(lambda: mock_open_browser.called)
                    mock_start.assert_called_once()

    mock_open_browser.assert_called_once_with("http://127.0.0.1:5173")
    mock_uvicorn.run.assert_called_once_with(
        mock_server.app, host="127.0.0.1", port=8524, log_level="info"
    )
    captured = capsys.readouterr()
    assert "Starting Vite dev server" in captured.out


def test_run_ui_command_falls_back_to_dist_when_vite_start_fails(capsys, monkeypatch):
    monkeypatch.setenv("CA_UI_DEV", "1")
    mock_open_browser = MagicMock()
    mock_uvicorn = MagicMock()
    mock_server = MagicMock(app=object())
    fake_modules = {
        "uvicorn": mock_uvicorn,
        "core.web.server": mock_server,
    }

    with patch.dict(sys.modules, fake_modules):
        with patch("core.cli.ui._frontend_source_exists", return_value=True):
            with patch("core.cli.ui._is_ui_dev_server_running", return_value=False):
                with patch("core.cli.ui._start_ui_dev_server", return_value=False):
                    with patch("core.cli.ui._frontend_dist_exists", return_value=True):
                        with patch(
                            "core.cli.helpers.find_available_port", return_value=8123
                        ):
                            with patch("core.cli.ui._open_browser", mock_open_browser):
                                with patch(
                                    "core.cli.helpers.is_tcp_port_open", return_value=True
                                ):
                                    assert ca_launcher.run_ui_command() == 0
                                    assert _wait_for(lambda: mock_open_browser.called)

    mock_open_browser.assert_called_once_with("http://127.0.0.1:8123")
    mock_uvicorn.run.assert_called_once_with(
        mock_server.app, host="127.0.0.1", port=8123, log_level="info"
    )
    captured = capsys.readouterr()
    assert "falling back to built UI" in captured.out


def test_main_new_command(monkeypatch):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "new", "my-task"])
    with patch("subprocess.run") as mock_run:
        ca_launcher.main()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "start_opencode.py" in cmd[1]
        assert "tasks/my-task.md" in cmd[2]


def test_main_engine_selection(monkeypatch):
    # Test selecting claude engine
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "claude", "do something"])
    with patch("subprocess.run") as mock_run:
        ca_launcher.main()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "start_claude_code.py" in cmd[1]
        assert "do something" in cmd
        assert "-y" in cmd


def test_main_default_engine_with_proxy(monkeypatch, capsys):
    # --proxy must precede the prompt/engine name (documented in EPILOG) to
    # be recognized as a real flag -- see
    # test_proxy_word_after_prompt_is_not_treated_as_a_flag for the opposite.
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "--proxy", "some task"])
    with patch("core.cli.helpers.is_tcp_port_open", return_value=True):
        with patch("subprocess.run") as mock_run:
            ca_launcher.main()
            args, kwargs = mock_run.call_args
            assert "start_gemini.py" in args[0][1]
            assert kwargs["env"] is not None
            assert "HTTP_PROXY" in kwargs["env"]
            captured = capsys.readouterr()
            assert (
                ca_launcher.t(
                    "proxy.enabled", scheme="http", host="127.0.0.1", port=1087
                )
                in captured.out
            )


def test_proxy_word_after_prompt_is_not_treated_as_a_flag(monkeypatch):
    # allow_interspersed_args=False means --proxy/-y appearing after the
    # engine name are literal prompt text, not flags that get silently
    # consumed -- otherwise merely mentioning "--proxy" in a task
    # description would turn the proxy on and delete the word from the
    # prompt sent to the engine.
    monkeypatch.setattr(
        "sys.argv",
        ["ca_launcher.py", "claude", "do", "something", "--proxy", "settings"],
    )
    with patch("subprocess.run") as mock_run:
        ca_launcher.main()
        args, kwargs = mock_run.call_args
        assert "start_claude_code.py" in args[0][1]
        assert "HTTP_PROXY" not in kwargs["env"]
        assert kwargs["env"][ca_launcher.CA_LANG_ENV] in ("en", "zh")
        assert args[0][2:] == ["do", "something", "--proxy", "settings", "-y"]


def test_main_passes_dash_p_through_to_engine(monkeypatch):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "claude", "-p", "hello"])
    with patch("subprocess.run") as mock_run:
        ca_launcher.main()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "start_claude_code.py" in cmd[1]
        assert "-p" in cmd
        assert "hello" in cmd
        assert "HTTP_PROXY" not in kwargs["env"]


def test_prompt_starting_with_a_reserved_word_still_launches_the_engine(monkeypatch):
    # "new"/"doctor"/"ui"/"history" are registered subcommand names, but a
    # prompt that happens to start with one of those words (e.g. "new" as
    # in "tell me what's new") must still reach the engine instead of
    # crashing with click's "unexpected extra arguments".
    monkeypatch.setattr(
        "sys.argv", ["ca_launcher.py", "new", "is", "broken", "please", "fix"]
    )
    with patch("subprocess.run") as mock_run:
        ca_launcher.main()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "start_gemini.py" in cmd[1]
        assert cmd[2:] == ["new", "is", "broken", "please", "fix", "-y"]


def test_history_prompt_words_still_launch_the_engine(monkeypatch):
    monkeypatch.setattr(
        "sys.argv", ["ca_launcher.py", "history", "please", "explain", "this"]
    )
    with patch("subprocess.run") as mock_run:
        ca_launcher.main()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "start_gemini.py" in cmd[1]
        assert cmd[2:] == ["history", "please", "explain", "this", "-y"]


def test_new_command_with_a_real_name_still_dispatches_to_new(monkeypatch):
    # Confirms the reserved-word fallback doesn't break genuine subcommand
    # usage -- "ca new my-task" must still create a task draft, not launch
    # the default engine with "new my-task" as a prompt.
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "new", "my-task"])
    with patch("subprocess.run") as mock_run:
        ca_launcher.main()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "start_opencode.py" in cmd[1]
        assert "tasks/my-task.md" in cmd[2]


def test_engine_exit_code_propagates_to_ca_process_exit(monkeypatch):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "claude", "do", "something"])
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=7)
        assert ca_launcher.main() == 7


def test_yolo_flag_is_not_inverted(monkeypatch):
    # -y/--yolo is documented as "enable YOLO mode" and defaults to True;
    # explicitly passing it must not flip the parsed value to False.
    captured = {}
    original = ca_launcher._launch_engine

    def spy(ctx, args):
        captured["yolo"] = ctx.obj["yolo"]
        return original(ctx, args)

    monkeypatch.setattr("core.cli.helpers._launch_engine", spy)
    with patch("subprocess.run"):
        ca_launcher.cli.main(["-y", "claude", "hi"], standalone_mode=False)
    assert captured["yolo"] is True


def test_build_proxy_env_falls_back_on_malformed_proxy_config():
    config = {"proxy": True}
    child_env, host, port, scheme = ca_launcher.build_proxy_env(config)
    assert host == "127.0.0.1"
    assert isinstance(port, int)


def test_project_root_survives_a_deleted_cwd(monkeypatch, tmp_path):
    def raise_oserror():
        raise OSError("No such file or directory")

    monkeypatch.setattr(ca_launcher.Path, "cwd", staticmethod(raise_oserror))
    with patch("core.cli.helpers._installed_root", return_value=tmp_path / "installed"):
        assert ca_launcher._project_root() == tmp_path / "installed"


def test_new_command_falls_back_to_absolute_path_on_relpath_failure(monkeypatch):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "new", "my-task"])

    def raise_value_error(*_args, **_kwargs):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    with patch("ca_launcher.os.path.relpath", side_effect=raise_value_error):
        with patch("subprocess.run") as mock_run:
            ca_launcher.main()
            args, _kwargs = mock_run.call_args
            assert "my-task.md" in args[0][2]


class _FakeRunStatus:
    def __init__(self, status, task_id):
        self.status = status
        self.task_id = task_id


def _write_fake_task(tasks_dir, name="code_review"):
    tasks_dir.mkdir(exist_ok=True)
    (tasks_dir / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")


def test_batch_run_dry_run_lists_targets_without_starting_anything(
    tmp_path, monkeypatch, capsys
):
    tasks_dir = tmp_path / "tasks"
    _write_fake_task(tasks_dir)
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks_dir))

    config = {
        "project_registry": [
            {"path": "/proj/a", "group": "work"},
            {"path": "/proj/b", "group": "common"},
        ]
    }
    monkeypatch.setattr(
        "sys.argv",
        [
            "ca_launcher.py",
            "batch-run",
            "code_review",
            "--engine",
            "claude",
            "--dry-run",
        ],
    )
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.cli.helpers.load_config", return_value=config),
        patch("core.cli.helpers._get_task_runner") as mock_get_runner,
    ):
        ca_launcher.main()
        mock_get_runner.assert_not_called()

    out = capsys.readouterr().out
    assert "/proj/a" in out
    assert "/proj/b" in out
    assert "dry run" in out


def test_batch_run_starts_per_project_and_skips_already_running(
    tmp_path, monkeypatch, capsys
):
    tasks_dir = tmp_path / "tasks"
    _write_fake_task(tasks_dir)
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks_dir))

    config = {
        "project_registry": [
            {"path": "/proj/a", "group": "work"},
            {"path": "/proj/b", "group": "work"},
            {"path": "/proj/c", "group": "other"},
        ]
    }

    class FakeRunner:
        def __init__(self):
            self.calls = []

        def run_task(
            self,
            task_name,
            engine,
            group,
            tasks_root=None,
            workspace=None,
            prevent_overlap=False,
        ):
            self.calls.append((task_name, engine, group, workspace))
            if workspace == "/proj/b":
                from core.services.runner_service import TaskAlreadyRunningError

                raise TaskAlreadyRunningError("already running")
            return _FakeRunStatus("running", "code_review_123")

    fake_runner = FakeRunner()
    monkeypatch.setattr(
        "sys.argv",
        [
            "ca_launcher.py",
            "batch-run",
            "code_review",
            "--engine",
            "claude",
            "--group",
            "work",
        ],
    )
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.cli.helpers.load_config", return_value=config),
        patch("core.cli.helpers._get_task_runner", return_value=fake_runner),
    ):
        ca_launcher.main()

    # --group work must exclude the "other" project entirely.
    assert fake_runner.calls == [
        ("code_review", "claude", "work", "/proj/a"),
        ("code_review", "claude", "work", "/proj/b"),
    ]
    out = capsys.readouterr().out
    assert "started code_review_123" in out
    assert "skipped, already running" in out
    assert "1 started, 1 skipped, 0 failed." in out


def test_batch_run_rejects_unknown_task_name(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    _write_fake_task(tasks_dir)
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks_dir))
    config = {"project_registry": [{"path": "/proj/a", "group": "work"}]}

    monkeypatch.setattr(
        "sys.argv",
        ["ca_launcher.py", "batch-run", "does-not-exist", "--engine", "claude"],
    )
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.cli.helpers.load_config", return_value=config),
        pytest.raises(SystemExit) as exc_info,
    ):
        ca_launcher.main()
    assert exc_info.value.code == 1


def test_batch_run_rejects_empty_group(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    _write_fake_task(tasks_dir)
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks_dir))
    config = {"project_registry": [{"path": "/proj/a", "group": "work"}]}

    monkeypatch.setattr(
        "sys.argv",
        [
            "ca_launcher.py",
            "batch-run",
            "code_review",
            "--engine",
            "claude",
            "--group",
            "nope",
        ],
    )
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.cli.helpers.load_config", return_value=config),
        pytest.raises(SystemExit) as exc_info,
    ):
        ca_launcher.main()
    assert exc_info.value.code == 1


def test_project_add_registers_non_interactively(tmp_path, monkeypatch, capsys):
    project_dir = tmp_path / "myproj"
    project_dir.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"groups": {"work": {}}, "project_registry": []}))

    monkeypatch.setattr(
        "sys.argv",
        ["ca_launcher.py", "project", "add", str(project_dir), "--group", "work"],
    )
    with patch("core.cli.helpers._project_root", return_value=tmp_path):
        ca_launcher.main()

    assert "Registered" in capsys.readouterr().out
    saved = json.loads(config_path.read_text())
    assert saved["project_registry"] == [
        {"path": str(project_dir.resolve()), "group": "work"}
    ]


def test_project_add_warns_on_unknown_group_but_still_registers(
    tmp_path, monkeypatch, capsys
):
    project_dir = tmp_path / "myproj"
    project_dir.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"groups": {}, "project_registry": []}))

    monkeypatch.setattr(
        "sys.argv",
        ["ca_launcher.py", "project", "add", str(project_dir), "--group", "ghost"],
    )
    with patch("core.cli.helpers._project_root", return_value=tmp_path):
        ca_launcher.main()

    out = capsys.readouterr().out
    assert "doesn't exist yet" in out
    assert "Registered" in out


def test_project_add_rejects_missing_directory(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"groups": {}, "project_registry": []}))
    missing = tmp_path / "does-not-exist"

    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "project", "add", str(missing)])
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        pytest.raises(SystemExit) as exc_info,
    ):
        ca_launcher.main()
    assert exc_info.value.code == 1


def test_project_remove(tmp_path, monkeypatch, capsys):
    project_dir = tmp_path / "myproj"
    project_dir.mkdir()
    resolved = str(project_dir.resolve())
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {"groups": {}, "project_registry": [{"path": resolved, "group": "work"}]}
        )
    )

    monkeypatch.setattr(
        "sys.argv", ["ca_launcher.py", "project", "remove", str(project_dir)]
    )
    with patch("core.cli.helpers._project_root", return_value=tmp_path):
        ca_launcher.main()

    assert "Removed" in capsys.readouterr().out
    saved = json.loads(config_path.read_text())
    assert saved["project_registry"] == []


def test_project_remove_unknown_path_exits_nonzero(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"groups": {}, "project_registry": []}))
    project_dir = tmp_path / "myproj"
    project_dir.mkdir()

    monkeypatch.setattr(
        "sys.argv", ["ca_launcher.py", "project", "remove", str(project_dir)]
    )
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        pytest.raises(SystemExit) as exc_info,
    ):
        ca_launcher.main()
    assert exc_info.value.code == 1


def test_project_list(tmp_path, monkeypatch, capsys):
    config = {
        "groups": {},
        "project_registry": [{"path": str(tmp_path), "group": "work"}],
    }
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "project", "list"])
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.cli.helpers.load_config", return_value=config),
    ):
        ca_launcher.main()

    out = capsys.readouterr().out
    assert str(tmp_path) in out
    assert "work" in out


def test_project_list_empty(tmp_path, monkeypatch, capsys):
    config = {"groups": {}, "project_registry": []}
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "project", "list"])
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.cli.helpers.load_config", return_value=config),
    ):
        ca_launcher.main()

    assert "No projects registered" in capsys.readouterr().out


def test_ensure_project_registered_hints_when_noninteractive(
    tmp_path, monkeypatch, capsys
):
    # root and the "external" cwd must be unrelated directories -- otherwise
    # _is_path_registered's own-install-root special case (cwd == root, or
    # root among cwd's parents) would make this look already-registered.
    root = tmp_path / "codeagent_root"
    root.mkdir()
    external = tmp_path / "external_project"
    external.mkdir()

    monkeypatch.delenv("CA_SKIP_AUTO_REGISTER", raising=False)
    monkeypatch.chdir(external)
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "claude", "hi"])
    config = {"project_registry": [], "groups": {}}
    with (
        patch("core.cli.helpers._project_root", return_value=root),
        patch("core.cli.helpers.load_config", return_value=config),
        patch("subprocess.run"),
    ):
        ca_launcher.main()

    err = capsys.readouterr().err
    assert "ca project add" in err
    assert str(external.resolve()) in err


def test_ensure_project_registered_silent_when_skip_env_set(
    tmp_path, monkeypatch, capsys
):
    root = tmp_path / "codeagent_root"
    root.mkdir()
    external = tmp_path / "external_project"
    external.mkdir()

    monkeypatch.setenv("CA_SKIP_AUTO_REGISTER", "1")
    monkeypatch.chdir(external)
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "claude", "hi"])
    config = {"project_registry": [], "groups": {}}
    with (
        patch("core.cli.helpers._project_root", return_value=root),
        patch("core.cli.helpers.load_config", return_value=config),
        patch("subprocess.run"),
    ):
        ca_launcher.main()

    assert capsys.readouterr().err == ""


def test_ensure_project_registered_silent_when_already_registered(
    tmp_path, monkeypatch, capsys
):
    root = tmp_path / "codeagent_root"
    root.mkdir()
    external = tmp_path / "external_project"
    external.mkdir()

    monkeypatch.delenv("CA_SKIP_AUTO_REGISTER", raising=False)
    monkeypatch.chdir(external)
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "claude", "hi"])
    config = {
        "project_registry": [{"path": str(external.resolve()), "group": "work"}],
        "groups": {},
    }
    with (
        patch("core.cli.helpers._project_root", return_value=root),
        patch("core.cli.helpers.load_config", return_value=config),
        patch("subprocess.run"),
    ):
        ca_launcher.main()

    assert capsys.readouterr().err == ""


def _mcp_config(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"groups": {}, "project_registry": []}))
    return config_path


def test_mcp_sync_reports_each_engine_result(tmp_path, monkeypatch, capsys):
    _mcp_config(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["ca_launcher.py", "mcp", "sync", "claude", "--to", "gemini"]
    )
    fake = MagicMock(
        return_value=[
            {"engine": "gemini", "name": "srv1", "action": "added", "detail": "ok"}
        ]
    )
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.services.mcp_service.sync_servers", fake),
    ):
        ca_launcher.main()

    out = capsys.readouterr().out
    assert "gemini" in out and "srv1" in out
    assert fake.call_args.kwargs["targets"] == ["gemini"]
    assert fake.call_args.kwargs["names"] is None


def test_mcp_sync_exits_nonzero_when_an_engine_fails(tmp_path, monkeypatch, capsys):
    _mcp_config(tmp_path)
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "mcp", "sync", "claude"])
    fake = MagicMock(
        return_value=[
            {"engine": "codex", "name": "srv1", "action": "failed", "detail": "boom"}
        ]
    )
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.services.mcp_service.sync_servers", fake),
        pytest.raises(SystemExit) as exc,
    ):
        ca_launcher.main()

    assert exc.value.code == 1
    assert "1 of 1 operations failed" in capsys.readouterr().out


def test_mcp_sync_rejects_an_invalid_request(tmp_path, monkeypatch, capsys):
    _mcp_config(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["ca_launcher.py", "mcp", "sync", "claude", "--to", "claude"]
    )
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch(
            "core.services.mcp_service.sync_servers",
            side_effect=ValueError("Cannot sync 'claude' onto itself"),
        ),
        pytest.raises(SystemExit) as exc,
    ):
        ca_launcher.main()

    assert exc.value.code == 1
    assert "onto itself" in capsys.readouterr().out


def test_mcp_list_covers_all_engines_by_default(tmp_path, monkeypatch, capsys):
    _mcp_config(tmp_path)
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "mcp", "list"])
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.services.mcp_service.list_servers", return_value=[]),
    ):
        ca_launcher.main()

    out = capsys.readouterr().out
    for engine in ("claude", "codex", "gemini", "opencode"):
        assert engine in out


def test_mcp_add_passes_command_and_env(tmp_path, monkeypatch, capsys):
    _mcp_config(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "ca_launcher.py",
            "mcp",
            "add",
            "claude",
            "fs",
            "--env",
            "LOG=debug",
            "--",
            "npx",
            "-y",
            "server-fs",
        ],
    )
    fake = MagicMock()
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.services.mcp_service.add_server", fake),
    ):
        ca_launcher.main()

    kwargs = fake.call_args.kwargs
    assert kwargs["command"] == ["npx", "-y", "server-fs"]
    assert kwargs["env"] == {"LOG": "debug"}
    assert kwargs["url"] is None
    out = capsys.readouterr().out
    assert "Added 'fs' to claude" in out
    # The point of the whole feature: nudge toward propagating it.
    assert "ca mcp sync claude" in out


def test_mcp_add_supports_a_url_server(tmp_path, monkeypatch):
    _mcp_config(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["ca_launcher.py", "mcp", "add", "codex", "api", "--url", "https://x/mcp"],
    )
    fake = MagicMock()
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.services.mcp_service.add_server", fake),
    ):
        ca_launcher.main()

    assert fake.call_args.kwargs["url"] == "https://x/mcp"
    assert fake.call_args.kwargs["command"] is None


def test_mcp_add_rejects_malformed_env(tmp_path, monkeypatch, capsys):
    _mcp_config(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["ca_launcher.py", "mcp", "add", "claude", "fs", "--env", "OOPS", "--", "x"],
    )
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.services.mcp_service.add_server") as fake,
        pytest.raises(SystemExit) as exc,
    ):
        ca_launcher.main()

    assert exc.value.code == 1
    assert "KEY=VALUE" in capsys.readouterr().out
    fake.assert_not_called()


def test_mcp_add_surfaces_a_cli_failure(tmp_path, monkeypatch, capsys):
    _mcp_config(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["ca_launcher.py", "mcp", "add", "claude", "fs", "--", "x"]
    )
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch(
            "core.services.mcp_service.add_server",
            side_effect=RuntimeError("'claude' CLI not found on PATH"),
        ),
        pytest.raises(SystemExit) as exc,
    ):
        ca_launcher.main()

    assert exc.value.code == 1
    assert "not found on PATH" in capsys.readouterr().out


def test_mcp_remove_reports_a_missing_server(tmp_path, monkeypatch, capsys):
    _mcp_config(tmp_path)
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "mcp", "remove", "gemini", "no"])
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.services.mcp_service.remove_server", side_effect=KeyError("no")),
        pytest.raises(SystemExit) as exc,
    ):
        ca_launcher.main()

    assert exc.value.code == 1
    assert "No such MCP server in gemini" in capsys.readouterr().out


def test_mcp_remove_succeeds(tmp_path, monkeypatch, capsys):
    _mcp_config(tmp_path)
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "mcp", "remove", "gemini", "fs"])
    fake = MagicMock()
    with (
        patch("core.cli.helpers._project_root", return_value=tmp_path),
        patch("core.services.mcp_service.remove_server", fake),
    ):
        ca_launcher.main()

    assert fake.call_args.args[0] == "gemini"
    assert fake.call_args.args[2] == "fs"
    assert "Removed 'fs' from gemini" in capsys.readouterr().out


# --- default engine ---------------------------------------------------------
#
# `ca` hard-coded gemini, so anyone working primarily in another engine had to
# name it on every single invocation.

_ENGINE_MAP = {"gemini": "g", "claude": "c", "opencode": "o", "codex": "x"}


def test_default_engine_falls_back_when_unset():
    assert ca_launcher._resolve_default_engine({}, _ENGINE_MAP) == "gemini"


@pytest.mark.parametrize("value", ["claude", "CLAUDE", "  codex  "])
def test_default_engine_honours_config(value):
    expected = value.strip().lower()
    assert (
        ca_launcher._resolve_default_engine({"default_engine": value}, _ENGINE_MAP)
        == expected
    )


def test_unknown_default_engine_warns_and_falls_back(capsys):
    """Worth saying out loud -- silently starting a different engine than the
    one configured would be its own surprise -- but not worth aborting over."""
    resolved = ca_launcher._resolve_default_engine(
        {"default_engine": "gpt5"}, _ENGINE_MAP
    )
    assert resolved == "gemini"
    stderr = capsys.readouterr().err
    assert "gpt5" in stderr
    assert "claude" in stderr  # lists what it does know
