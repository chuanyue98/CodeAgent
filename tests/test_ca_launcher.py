import json
import sys
from unittest.mock import MagicMock, patch

import pytest
import ca_launcher


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
    with patch("ca_launcher._project_root", return_value=tmp_path):
        config = ca_launcher.load_config()
        assert config["default_mode"] == "local"
        assert config["proxy"]["port"] == 1087


def test_load_config_custom(mock_config, monkeypatch):
    # Test loading custom config.json
    monkeypatch.chdir(mock_config.parent)
    with patch("ca_launcher._project_root", return_value=mock_config.parent):
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
    with patch("ca_launcher.is_tcp_port_open", return_value=True):
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

    with patch("ca_launcher._installed_root", return_value=tmp_path / "installed"):
        assert ca_launcher._project_root() == workspace


def test_main_help(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "--help"])
    ca_launcher.main()
    captured = capsys.readouterr()
    assert "Usage:" in captured.out
    assert "CodeAgent: Professional AI Engineering Shell" in captured.out


def test_main_ui_command(monkeypatch):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "ui"])
    with patch("ca_launcher.run_ui_command", return_value=0) as mock_ui:
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
        with patch("ca_launcher._frontend_source_exists", return_value=True):
            with patch("ca_launcher._is_ui_dev_server_running", return_value=True):
                with patch("ca_launcher._open_browser", mock_open_browser):
                    assert ca_launcher.run_ui_command() == 0

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
        with patch("ca_launcher._frontend_source_exists", return_value=True):
            with patch("ca_launcher._is_ui_dev_server_running", return_value=False):
                with patch(
                    "ca_launcher._start_ui_dev_server", return_value=True
                ) as mock_start:
                    with patch("ca_launcher._open_browser", mock_open_browser):
                        assert ca_launcher.run_ui_command() == 0
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
        with patch("ca_launcher._frontend_source_exists", return_value=True):
            with patch("ca_launcher._is_ui_dev_server_running", return_value=False):
                with patch("ca_launcher._start_ui_dev_server", return_value=False):
                    with patch("ca_launcher._frontend_dist_exists", return_value=True):
                        with patch(
                            "ca_launcher.find_available_port", return_value=8123
                        ):
                            with patch("ca_launcher._open_browser", mock_open_browser):
                                assert ca_launcher.run_ui_command() == 0

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
    with patch("ca_launcher.is_tcp_port_open", return_value=True):
        with patch("subprocess.run") as mock_run:
            ca_launcher.main()
            args, kwargs = mock_run.call_args
            assert "start_gemini.py" in args[0][1]
            assert kwargs["env"] is not None
            assert "HTTP_PROXY" in kwargs["env"]
            captured = capsys.readouterr()
            assert "🌐 代理已启用" in captured.out


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
        assert kwargs["env"] is None
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
        assert kwargs["env"] is None


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

    monkeypatch.setattr(ca_launcher, "_launch_engine", spy)
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
    with patch("ca_launcher._installed_root", return_value=tmp_path / "installed"):
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
        ["ca_launcher.py", "batch-run", "code_review", "--engine", "claude", "--dry-run"],
    )
    with (
        patch("ca_launcher._project_root", return_value=tmp_path),
        patch("ca_launcher.load_config", return_value=config),
        patch("ca_launcher._get_task_runner") as mock_get_runner,
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
            self, task_name, engine, group, tasks_root=None, workspace=None,
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
        ["ca_launcher.py", "batch-run", "code_review", "--engine", "claude", "--group", "work"],
    )
    with (
        patch("ca_launcher._project_root", return_value=tmp_path),
        patch("ca_launcher.load_config", return_value=config),
        patch("ca_launcher._get_task_runner", return_value=fake_runner),
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
        patch("ca_launcher._project_root", return_value=tmp_path),
        patch("ca_launcher.load_config", return_value=config),
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
        ["ca_launcher.py", "batch-run", "code_review", "--engine", "claude", "--group", "nope"],
    )
    with (
        patch("ca_launcher._project_root", return_value=tmp_path),
        patch("ca_launcher.load_config", return_value=config),
        pytest.raises(SystemExit) as exc_info,
    ):
        ca_launcher.main()
    assert exc_info.value.code == 1
