"""Top-level Click entry point — replaces the monolithic ``ca_launcher.py``."""

from __future__ import annotations

import sys

import click

from core.engine_registry import ENGINES
from core.host_env import child_environ
from core.i18n import ENV_VAR as CA_LANG_ENV
from core.i18n import resolve_language, t

from . import helpers as _helpers_mod
from .commands.history import history
from .commands.mcp import mcp
from .commands.project import project
from .commands.resources import resources
from .commands.resume import resume, resume_session_flow
from .commands.status import status
from .commands.switch import switch
from .commands.sync import sync
from .commands.tasks import batch_run, doctor, new, ps, stop, ui
from .helpers import init_cli_runtime

EPILOG = """\
Engines: opencode, claude, codex, codebuddy, antigravity (agy)

YOLO mode is enabled by default.

\b
Examples:
  ca                       Open interactive launcher console (in terminal)
  ca menu                  Same as bare ca
  ca claude                Start Claude Code
  ca codex                 Start OpenAI Codex
  ca opencode              Start OpenCode
  ca agy                   Start Google Antigravity
  ca -r                    List and resume recent sessions across all engines
  ca -r 2                  Resume the 2nd most recent session directly
  ca resume                Same as ca -r (supports --engine <name>)
  ca -s                    Switch a session to another engine interactively
  ca -s codex              Switch current session to Codex (Enter to confirm)
  ca -s codex 2            Switch 2nd session to Codex directly
  ca switch codex          Same as ca -s codex
  ca status                Show current project, group, and standards status
  ca sync                  Install standards and skills into project AGENTS.md
  ca doctor --fix          Run health check and auto-repair
  ca ui                    Start the Web UI
  ca mcp install           Install CodeAgent MCP server into all engines
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
    def parse_args(self, ctx, args):  # type: ignore[no-untyped-def]
        new_args = list(args)
        for i, arg in enumerate(new_args):
            if arg in ("-s", "--switch", "s"):
                new_args[i] = "switch"
                break
            elif not arg.startswith("-"):
                break
        return super().parse_args(ctx, new_args)

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
    "-y",
    "--yolo",
    is_flag=True,
    default=False,
    help="Enable YOLO mode (bypass sandbox and approvals)",
)
@click.option(
    "-r",
    "--resume",
    "resume_selector",
    is_flag=False,
    flag_value="",
    default=None,
    help="Resume a previous session (list sessions or pass index/ID)",
)
@click.option(
    "-e",
    "--engine",
    "resume_engine",
    default=None,
    help="Filter sessions by engine when resuming",
)
@click.option(
    "--no-launch",
    is_flag=True,
    default=False,
    help="Print the command without starting the engine",
)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    default=False,
    help="Launch interactive console menu",
)
@click.pass_context
def cli(ctx, proxy, yolo, resume_selector, resume_engine, no_launch, interactive):  # type: ignore[no-untyped-def]
    """CodeAgent: Professional AI Engineering Shell."""
    init_cli_runtime()
    ctx.ensure_object(dict)
    config = _helpers_mod.load_config()
    root = _helpers_mod._project_root()
    # Derived from the declarative engine registry (core.engine_registry):
    # canonical names plus every alias ("ca agy") map to the launch script.
    engine_script_map = {
        key: str(root / "engines" / spec.launch_script)
        for spec in ENGINES.values()
        for key in (spec.name, *spec.aliases)
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
        if resume_selector is not None:
            return resume_session_flow(
                ctx,
                selector=resume_selector,
                engine=resume_engine,
                no_launch=no_launch,
            )
        if interactive or (sys.stdin.isatty() and sys.stdout.isatty()):
            from .launcher_menu import run_interactive_launcher

            return run_interactive_launcher(ctx)

        click.echo(ctx.get_help())
        return 0


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
    name="menu",
    help="Open the interactive launcher console",
)
@click.pass_context
def menu(ctx):  # type: ignore[no-untyped-def]
    from .launcher_menu import run_interactive_launcher

    return run_interactive_launcher(ctx)


# Register extracted subcommands — keeps the original ``ca history`` / ``ca mcp`` etc. names.
cli.add_command(history)
cli.add_command(mcp)
cli.add_command(project)
cli.add_command(resources)
cli.add_command(status)
cli.add_command(resume)
cli.add_command(ps)
cli.add_command(stop)
cli.add_command(batch_run)
cli.add_command(doctor)
cli.add_command(new)
cli.add_command(ui)
cli.add_command(switch)
cli.add_command(sync)
cli.add_command(menu)


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
