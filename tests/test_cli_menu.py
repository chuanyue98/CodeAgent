"""Tests for the interactive launcher console (``ca`` bare and ``ca menu``)."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from core.cli.main import cli


def test_cli_bare_non_interactive_prints_help():
    """When stdin is not a TTY, bare ``ca`` prints help without entering menu."""
    runner = CliRunner()
    result = runner.invoke(cli, [])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "Options:" in result.output


def test_cli_menu_subcommand_invokes_interactive_launcher():
    """``ca menu`` explicitly runs the interactive launcher."""
    runner = CliRunner()
    with patch("core.cli.launcher_menu.run_interactive_launcher", return_value=0) as mock_menu:
        result = runner.invoke(cli, ["menu"])
        assert result.exit_code == 0
        assert mock_menu.called


def test_cli_flag_interactive_invokes_interactive_launcher():
    """``ca -i`` runs the interactive launcher even if non-TTY."""
    runner = CliRunner()
    with patch("core.cli.launcher_menu.run_interactive_launcher", return_value=0) as mock_menu:
        result = runner.invoke(cli, ["-i"])
        assert result.exit_code == 0
        assert mock_menu.called


def test_interactive_launcher_exit():
    """User selects 'exit' in the menu."""
    runner = CliRunner()
    with patch("questionary.select") as mock_select:
        mock_prompt = MagicMock()
        mock_prompt.ask.return_value = "exit"
        mock_select.return_value = mock_prompt

        result = runner.invoke(cli, ["-i"])
        assert result.exit_code == 0


def test_interactive_launcher_resume_latest():
    """User selects 'resume_latest' in the menu."""
    runner = CliRunner()
    with patch("questionary.select") as mock_select:
        mock_prompt = MagicMock()
        mock_prompt.ask.return_value = "resume_latest"
        mock_select.return_value = mock_prompt

        with patch("core.cli.launcher_menu.resume_session_flow", return_value=0) as mock_resume:
            result = runner.invoke(cli, ["-i"])
            assert result.exit_code == 0
            mock_resume.assert_called_once()
            _, kwargs = mock_resume.call_args
            assert kwargs.get("selector") == "1"


def test_interactive_launcher_browse_sessions():
    """User selects 'browse_sessions' in the menu."""
    runner = CliRunner()
    with patch("questionary.select") as mock_select:
        mock_prompt = MagicMock()
        mock_prompt.ask.return_value = "browse_sessions"
        mock_select.return_value = mock_prompt

        with patch("core.cli.launcher_menu.resume_session_flow", return_value=0) as mock_resume:
            result = runner.invoke(cli, ["-i"])
            assert result.exit_code == 0
            mock_resume.assert_called_once()
            _, kwargs = mock_resume.call_args
            assert kwargs.get("selector") == ""


def test_interactive_launcher_launch_engine():
    """User selects 'launch_engine' and picks 'claude'."""
    runner = CliRunner()
    with patch("questionary.select") as mock_select:
        prompt_action = MagicMock()
        prompt_action.ask.return_value = "launch_engine"

        prompt_engine = MagicMock()
        prompt_engine.ask.return_value = "claude"

        mock_select.side_effect = [prompt_action, prompt_engine]

        with patch("core.cli.helpers._launch_engine", return_value=0) as mock_launch:
            result = runner.invoke(cli, ["-i"])
            assert result.exit_code == 0
            mock_launch.assert_called_once()
            args = mock_launch.call_args[0]
            assert args[1] == ["claude"]


def test_interactive_launcher_switch():
    """User selects 'switch_session' in the menu."""
    runner = CliRunner()
    with patch("questionary.select") as mock_select:
        mock_prompt = MagicMock()
        mock_prompt.ask.return_value = "switch_session"
        mock_select.return_value = mock_prompt

        with patch("click.Context.invoke") as mock_invoke:
            mock_invoke.return_value = 0
            result = runner.invoke(cli, ["-i"])
            assert result.exit_code == 0
            assert mock_invoke.called


def test_interactive_launcher_more_sync():
    """User selects 'more' -> 'sync' in the menu."""
    runner = CliRunner()
    with patch("questionary.select") as mock_select:
        prompt_action = MagicMock()
        prompt_action.ask.return_value = "more"

        prompt_more = MagicMock()
        prompt_more.ask.return_value = "sync"

        mock_select.side_effect = [prompt_action, prompt_more]

        with patch("click.Context.invoke") as mock_invoke:
            mock_invoke.return_value = 0
            result = runner.invoke(cli, ["-i"])
            assert result.exit_code == 0
            assert mock_invoke.called
