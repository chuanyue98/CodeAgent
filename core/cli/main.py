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
from .commands.tasks import batch_run, doctor, new, ps, stop, ui
from .helpers import init_cli_runtime

#: 供 ``ca_launcher`` 与测试沿用的老名字；内容现在跟随语言设置。
EPILOG = t("cli.epilog")


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
        super().parse_args(ctx, new_args)
        # ``-r`` 的值可省略，``ca -r -e codex 2`` 里它紧跟着一个选项，于是
        # 拿到空值，``2`` 落进子命令位。不是已知子命令的，就还给 ``-r``。
        if ctx.params.get("resume_selector") == "" and ctx._protected_args:
            first = ctx._protected_args[0]
            if not first.startswith("-") and self.get_command(ctx, first) is None:
                ctx.params["resume_selector"] = first
                ctx._protected_args, ctx.args = ctx.args[:1], ctx.args[1:]
        return ctx.args

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
    help=t("cli.desc.root"),
    epilog=EPILOG,
)
@click.option("--proxy", is_flag=True, help=t("cli.help.proxy"))
@click.option(
    "-y",
    "--yolo",
    is_flag=True,
    default=False,
    help=t("cli.help.yolo"),
)
@click.option(
    "-r",
    "--resume",
    "resume_selector",
    is_flag=False,
    flag_value="",
    default=None,
    help=t("cli.help.resume"),
)
@click.option(
    "-e",
    "--engine",
    "resume_engine",
    default=None,
    help=t("cli.help.resume_engine"),
)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    default=False,
    help=t("cli.help.interactive"),
)
@click.pass_context
def cli(ctx, proxy, yolo, resume_selector, resume_engine, interactive):  # type: ignore[no-untyped-def]
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
    help=t("cli.desc.menu"),
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
