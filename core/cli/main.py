"""Top-level Click entry point — replaces the monolithic ``ca_launcher.py``."""

from __future__ import annotations

import sys

import click

from core.host_env import child_environ
from core.i18n import ENV_VAR as CA_LANG_ENV
from core.i18n import resolve_language, t

from . import helpers as _helpers_mod
from .commands.history import history
from .commands.mcp import mcp
from .commands.project import project
from .commands.resources import resources
from .commands.switch import switch
from .commands.tasks import batch_run, doctor, new, ps, stop, ui
from .helpers import init_cli_runtime

EPILOG = """\
Engines: opencode, claude, codex, codebuddy, antigravity (agy)
         (default: opencode; set "default_engine" in config.json to change)

YOLO mode is enabled by default.

\\b
Examples:
  ca                       Start the default engine
  ca claude do something   Start claude with extra args
  ca --proxy opencode      Start opencode with proxy enabled
  ca doctor --fix          Run health check and auto-repair
  ca ui                    Start the Web UI
  ca new my-task           Create a new task draft
  ca ps                    List running background task runs
  ca stop <task_id>        Stop a background task run
  ca batch-run code_review --engine claude --group work
                           Run one task across every registered project in a group
  ca project add . --group work
                           Register the current directory, non-interactively
  ca project list         List every registered project
  ca history list          List sessions (use --engine <name> to filter)
  ca history show <engine> <session_id>
  ca history convert <source_engine> <session_id> <target_engine>
"""


def _reserved_command_can_handle(cmd, parent_ctx, cmd_name, rest):  # type: ignore[no-untyped-def]
    try:
        sub_ctx = cmd.make_context(cmd_name, list(rest), parent=parent_ctx)
    except click.UsageError as exc:
        if rest and rest[0].startswith("-"):
            return False, exc
        return False, None
    if isinstance(cmd, click.Group) and rest:
        first = rest[0]
        if not first.startswith("-") and cmd.get_command(sub_ctx, first) is None:
            return False, None
    return True, None


class CodeAgentGroup(click.Group):
    def resolve_command(self, ctx, args):  # type: ignore[no-untyped-def]
        if args:
            cmd_name = args[0]
            cmd = self.get_command(ctx, cmd_name)
            if cmd is not None:
                handled, error = _reserved_command_can_handle(
                    cmd, ctx, cmd_name, args[1:]
                )
                if handled:
                    return cmd_name, cmd, args[1:]
                if error is not None:
                    raise error
        launch = self.get_command(ctx, "_launch")
        return "_launch", launch, args


@click.group(
    cls=CodeAgentGroup,
    invoke_without_command=True,
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
        allow_interspersed_args=False,
    ),
    epilog=EPILOG,
)
@click.option("--proxy", is_flag=True, help="Enable proxy from config.json")
@click.option(
    "-y", "--yolo", is_flag=True, flag_value=True, default=True, help="Enable YOLO mode"
)
@click.pass_context
def cli(ctx, proxy, yolo):  # type: ignore[no-untyped-def]
    """CodeAgent: Professional AI Engineering Shell."""
    init_cli_runtime()
    ctx.ensure_object(dict)
    config = _helpers_mod.load_config()
    root = _helpers_mod._project_root()
    engine_script_map = {
        "claude": str(root / "engines" / "start_claude_code.py"),
        "opencode": str(root / "engines" / "start_opencode.py"),
        "codex": str(root / "engines" / "start_codex.py"),
        "codebuddy": str(root / "engines" / "start_codebuddy.py"),
        "antigravity": str(root / "engines" / "start_antigravity.py"),
        "agy": str(root / "engines" / "start_antigravity.py"),
    }
    child_env = None
    if proxy:
        child_env, proxy_host, proxy_port, proxy_scheme = _helpers_mod.build_proxy_env(
            config
        )
        print(t("proxy.enabled", scheme=proxy_scheme, host=proxy_host, port=proxy_port))
    child_env = child_env if child_env is not None else child_environ()
    child_env[CA_LANG_ENV] = resolve_language()
    ctx.obj.update(
        config=config,
        root=root,
        engine_script_map=engine_script_map,
        child_env=child_env,
        proxy=proxy,
        yolo=yolo,
    )
    if ctx.invoked_subcommand is None:
        return _helpers_mod._launch_engine(ctx, [])


@cli.command(
    name="_launch",
    hidden=True,
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.argument("args", nargs=-1)
@click.pass_context
def _launch(ctx, args):  # type: ignore[no-untyped-def]
    return _helpers_mod._launch_engine(ctx, list(args))


@cli.command(
    name="antigravity",
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
        add_help_option=False,
    ),
    help="Start the Google Antigravity engine",
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def antigravity_cmd(ctx, args):  # type: ignore[no-untyped-def]
    return _helpers_mod._launch_engine(ctx, ["antigravity", *args])


@cli.command(
    name="agy",
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
        add_help_option=False,
    ),
    help="Alias for ca antigravity",
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def agy_cmd(ctx, args):  # type: ignore[no-untyped-def]
    return _helpers_mod._launch_engine(ctx, ["agy", *args])


# Register extracted subcommands — keeps the original ``ca history`` / ``ca mcp`` etc. names.
cli.add_command(history)
cli.add_command(mcp)
cli.add_command(project)
cli.add_command(resources)
cli.add_command(ps)
cli.add_command(stop)
cli.add_command(batch_run)
cli.add_command(doctor)
cli.add_command(new)
cli.add_command(ui)
cli.add_command(switch)


def main():  # type: ignore[no-untyped-def]
    try:
        return cli(standalone_mode=False)
    except click.ClickException as e:
        e.show()
        sys.exit(e.exit_code)
    except click.exceptions.Abort:
        sys.exit(1)
    except KeyboardInterrupt:
        print(t("cli.cancelled"))
        sys.exit(0)
