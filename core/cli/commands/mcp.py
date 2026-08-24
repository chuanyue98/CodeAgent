"""``ca mcp`` command group."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from core.constants import ENGINES
from core.i18n import t

from .. import helpers as _helpers

_ENGINE_CHOICE = click.Choice(sorted(ENGINES))


@click.group(name="mcp", invoke_without_command=True)
@click.pass_context
def mcp(ctx):  # type: ignore[no-untyped-def]
    """Inspect and sync MCP servers across engines."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@mcp.command(name="list")
@click.argument("engine", type=_ENGINE_CHOICE, required=False)
@click.pass_context
def mcp_list(ctx, engine):  # type: ignore[no-untyped-def]
    """List configured MCP servers for ENGINE (default: all four)."""
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.services import mcp_service

    project_path = str(Path.cwd())
    engines = [engine] if engine else sorted(ENGINES)
    for name in engines:
        try:
            servers = mcp_service.list_servers(name, project_path)
        except Exception as exc:
            click.echo(f"{click.style(name, bold=True)}: ⚠️  {exc}")
            continue
        scope = "project" if name == "claude" else "global"
        header = f"{name} ({scope})"
        if not servers:
            click.echo(f"{click.style(header, bold=True)}: (none)")
            continue
        click.echo(click.style(f"{header} — {len(servers)}", bold=True))
        for server in servers:
            target = server["url"] or " ".join(server["command"] or [])
            click.echo(f"  ● {server['name']}  [{server['transport']}]  {target}")


@mcp.command(name="add")
@click.argument("engine", type=_ENGINE_CHOICE)
@click.argument("name")
@click.argument("command", nargs=-1)
@click.option("--url", default=None, help="Remote server URL, instead of a command.")
@click.option(
    "--env",
    "env_pairs",
    multiple=True,
    metavar="KEY=VALUE",
    help="Environment variable for the server; repeatable.",
)
@click.option(
    "--transport",
    default=None,
    help="Transport for a --url server (e.g. http, sse). Ignored for stdio.",
)
@click.pass_context
def mcp_add(ctx, engine, name, command, url, env_pairs, transport):  # type: ignore[no-untyped-def]
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.services import mcp_service

    env: dict[str, str] = {}
    for pair in env_pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            print(t("mcp.bad_env_pair", pair=pair))
            sys.exit(1)
        env[key] = value
    try:
        mcp_service.add_server(
            engine,
            str(Path.cwd()),
            name,
            command=list(command) or None,
            url=url,
            env=env or None,
            transport=transport,
        )
    except (ValueError, RuntimeError) as exc:
        print(t("mcp.error", error=exc))
        sys.exit(1)
    scope = t("mcp.scope_project") if engine == "claude" else t("mcp.scope_global")
    print(t("mcp.added", name=name, engine=engine, scope=scope))
    others = sorted(ENGINES - {engine})
    print(t("mcp.sync_hint", engine=engine))
    print(t("mcp.sync_targets", targets=", ".join(others)))


@mcp.command(name="remove")
@click.argument("engine", type=_ENGINE_CHOICE)
@click.argument("name")
@click.pass_context
def mcp_remove(ctx, engine, name):  # type: ignore[no-untyped-def]
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.services import mcp_service

    try:
        mcp_service.remove_server(engine, str(Path.cwd()), name)
    except KeyError:
        print(t("mcp.not_found", engine=engine, name=name))
        sys.exit(1)
    except (ValueError, RuntimeError) as exc:
        print(t("mcp.error", error=exc))
        sys.exit(1)
    print(t("mcp.removed", name=name, engine=engine))


@mcp.command(name="sync")
@click.argument("source", type=_ENGINE_CHOICE)
@click.option(
    "--to",
    "targets",
    multiple=True,
    type=_ENGINE_CHOICE,
    help="Target engine; repeatable. Defaults to every engine but SOURCE.",
)
@click.option(
    "--name",
    "names",
    multiple=True,
    help="Only sync this server; repeatable. Defaults to all of SOURCE's.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Replace same-named servers in the targets instead of skipping them.",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would change without writing anything."
)
@click.pass_context
def mcp_sync(ctx, source, targets, names, overwrite, dry_run):  # type: ignore[no-untyped-def]
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.services import mcp_service

    try:
        results = mcp_service.sync_servers(
            source,
            str(Path.cwd()),
            targets=list(targets) or None,
            names=list(names) or None,
            overwrite=overwrite,
            dry_run=dry_run,
        )
    except ValueError as exc:
        print(t("mcp.error", error=exc))
        sys.exit(1)
    if not results:
        print(t("mcp.nothing_to_sync", source=source))
        return
    marks = {
        "added": click.style("+", fg="green"),
        "replaced": click.style("~", fg="yellow"),
        "skipped": click.style("=", fg="bright_black"),
        "failed": click.style("!", fg="red"),
    }
    if dry_run:
        click.echo(click.style(t("mcp.dry_run"), bold=True))
    for engine_name in dict.fromkeys(item["engine"] for item in results):
        click.echo(click.style(engine_name, bold=True))
        for item in (r for r in results if r["engine"] == engine_name):
            mark = marks.get(item["action"], "?")
            click.echo(f"  {mark} {item['name']} — {item['detail']}")
    failed = sum(1 for item in results if item["action"] == "failed")
    if failed:
        print(t("mcp.partial_failure", failed=failed, total=len(results)))
        sys.exit(1)


@mcp.command(name="serve")
@click.option(
    "--http",
    is_flag=True,
    help="以 Streamable HTTP 模式运行(默认 stdio,桌面工具子进程拉起即用)。",
)
@click.option("--port", default=8525, type=int, help="HTTP 模式端口(默认 8525)。")
@click.option(
    "--group",
    default=None,
    help="按 config.json 的组过滤技能,如 --group work;默认挂载全部。",
)
@click.pass_context
def mcp_serve(ctx, http, port, group):  # type: ignore[no-untyped-def]
    """Serve CodeAgent assets (skills) as an MCP server (read-only).

    把 CodeAgent 自己的 skills 按 MCP 标准暴露成 tools/resources,
    让任何支持 MCP 的客户端(CodeBuddy / Trae / Cursor / claude / codex)
    都能直接消费。默认只读,不接触任何 API 密钥。

    在客户端里连接:
      stdio:  uv run python -m core.services.mcp_server_service(或 ca mcp serve 的子进程命令)
      http:   http://127.0.0.1:8525
    """
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.services.mcp_server_service import serve

    try:
        serve(
            config=ctx.obj["config"],
            group=group,
            transport="http" if http else "stdio",
            port=port,
        )
    except RuntimeError as exc:
        print(click.style(f"✗ {exc}", fg="red"))
        sys.exit(1)
