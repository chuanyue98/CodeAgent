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
    # Patch Path.resolve().parent to point to tmp_path
    with patch("ca_launcher.Path") as mock_path:
        mock_path.return_value.resolve.return_value.parent = tmp_path
        config = ca_launcher.load_config()
        assert config["default_mode"] == "local"
        assert config["proxy"]["port"] == 1087


def test_load_config_custom(mock_config, monkeypatch):
    # Test loading custom config.json
    monkeypatch.chdir(mock_config.parent)
    with patch("ca_launcher.Path") as mock_path:
        mock_path.return_value.resolve.return_value.parent = mock_config.parent
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
        # First port taken (8000), second free (8001)
        mock_s.connect_ex.side_effect = [0, 1]
        assert ca_launcher.find_available_port(8000) == 8001


def test_build_proxy_env():
    config = {"proxy": {"host": "myproxy", "port": 3066}}
    with patch("ca_launcher.is_tcp_port_open", return_value=True):
        env, host, port, scheme = ca_launcher.build_proxy_env(config)
        assert host == "myproxy"
        assert port == 3066
        assert scheme == "socks5"
        assert env["HTTP_PROXY"] == "socks5://myproxy:3066"


def test_main_help(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "--help"])
    ca_launcher.main()
    captured = capsys.readouterr()
    assert "Usage: python ca_launcher.py" in captured.out


def test_main_ui_command(monkeypatch):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "ui"])
    with patch("ca_launcher.run_ui_command", return_value=0) as mock_ui:
        assert ca_launcher.main() == 0
        mock_ui.assert_called_once()


def test_run_ui_command_uses_existing_vite_server(capsys):
    mock_webbrowser = MagicMock()
    mock_uvicorn = MagicMock()
    mock_server = MagicMock(app=object())
    fake_modules = {
        "webbrowser": mock_webbrowser,
        "uvicorn": mock_uvicorn,
        "core.web.server": mock_server,
    }

    with patch.dict(sys.modules, fake_modules):
        with patch("ca_launcher._frontend_source_exists", return_value=True):
            with patch("ca_launcher._is_ui_dev_server_running", return_value=True):
                assert ca_launcher.run_ui_command() == 0

    mock_webbrowser.open.assert_called_once_with("http://127.0.0.1:5173")
    mock_uvicorn.run.assert_called_once_with(
        mock_server.app, host="127.0.0.1", port=8000, log_level="info"
    )
    captured = capsys.readouterr()
    assert "Detected Vite dev server" in captured.out


def test_run_ui_command_starts_vite_server_when_available(capsys):
    mock_webbrowser = MagicMock()
    mock_uvicorn = MagicMock()
    mock_server = MagicMock(app=object())
    fake_modules = {
        "webbrowser": mock_webbrowser,
        "uvicorn": mock_uvicorn,
        "core.web.server": mock_server,
    }

    with patch.dict(sys.modules, fake_modules):
        with patch("ca_launcher._frontend_source_exists", return_value=True):
            with patch("ca_launcher._is_ui_dev_server_running", return_value=False):
                with patch(
                    "ca_launcher._start_ui_dev_server", return_value=True
                ) as mock_start:
                    assert ca_launcher.run_ui_command() == 0
                    mock_start.assert_called_once()

    mock_webbrowser.open.assert_called_once_with("http://127.0.0.1:5173")
    mock_uvicorn.run.assert_called_once_with(
        mock_server.app, host="127.0.0.1", port=8000, log_level="info"
    )
    captured = capsys.readouterr()
    assert "Starting Vite dev server" in captured.out


def test_run_ui_command_falls_back_to_dist_when_vite_start_fails(capsys):
    mock_webbrowser = MagicMock()
    mock_uvicorn = MagicMock()
    mock_server = MagicMock(app=object())
    fake_modules = {
        "webbrowser": mock_webbrowser,
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
                            assert ca_launcher.run_ui_command() == 0

    mock_webbrowser.open.assert_called_once_with("http://127.0.0.1:8123")
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
    # Test default engine (gemini) with proxy flag
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "some task", "--proxy"])
    with patch("ca_launcher.is_tcp_port_open", return_value=True):
        with patch("subprocess.run") as mock_run:
            ca_launcher.main()
            args, kwargs = mock_run.call_args
            assert "start_gemini.py" in args[0][1]
            assert kwargs["env"] is not None
            assert "HTTP_PROXY" in kwargs["env"]
            captured = capsys.readouterr()
            assert "🌐 代理已启用" in captured.out


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
