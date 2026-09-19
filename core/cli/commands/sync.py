"""``ca sync`` command."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from core.constants import ENGINES
from core.i18n import t
from core.services.sync_service import STANDARDS_FILENAME

from .. import helpers as _helpers

_ENGINE_CHOICE = click.Choice(sorted(ENGINES))

_MARKS = {
    "write": click.style("+", fg="green"),
    "update": click.style("~", fg="yellow"),
    "unchanged": click.style("=", fg="bright_black"),
    "remove": click.style("-", fg="red"),
    "conflict": click.style("!", fg="yellow"),
    "failed": click.style("x", fg="red"),
}


@click.command(name="sync")
@click.option(
    "--group",
    default=None,
    help="Resource group to sync. Defaults to default_group in config.json.",
)
@click.option(
    "--engine",
    "engines",
    multiple=True,
    type=_ENGINE_CHOICE,
    help="Only sync this engine's skills; repeatable. Defaults to every engine.",
)
@click.option(
    "--project",
    "project_root",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Project whose AGENTS.md takes the standards. Defaults to the current directory.",
)
@click.option(
    "--user",
    "user_scope",
    is_flag=True,
    help=(
        "Write the standards into each engine's user-level config instead of the "
        "project's AGENTS.md; meant for cleaning up older syncs."
    ),
)
@click.option(
    "--remove",
    is_flag=True,
    help="Remove what `ca sync` wrote instead of writing it.",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would change without writing anything."
)
@click.pass_context
def sync(ctx, group, engines, project_root, user_scope, remove, dry_run):  # type: ignore[no-untyped-def]
    """Write the group's standards into the project's AGENTS.md, and its skills
    into each engine's user-level skill directory."""
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.services import sync_service

    try:
        group_name, items = sync_service.sync(
            group=group,
            engines=list(engines) or None,
            remove=remove,
            dry_run=dry_run,
            scope="user" if user_scope else "project",
            root=project_root,
        )
    except ValueError as exc:
        print(t("sync.error", error=exc))
        sys.exit(1)

    if dry_run:
        click.echo(click.style(t("sync.dry_run"), bold=True))
    if remove:
        click.echo(t("sync.removing"))
    else:
        click.echo(t("sync.group", group=group_name, file=STANDARDS_FILENAME))
    if user_scope:
        click.echo(click.style(t("sync.user_scope"), fg="yellow"))

    # 规范只有一条，不属于任何引擎；技能按引擎分组。
    for item in items:
        if item.kind == "standards":
            click.echo(f"  {_MARKS.get(item.action, '?')} {item.name}")
    for engine_name in dict.fromkeys(item.engine for item in items if item.engine):
        click.echo(click.style(engine_name, bold=True))
        for item in (i for i in items if i.engine == engine_name):
            click.echo(f"  {_MARKS.get(item.action, '?')} skills/{item.name}")

    conflicts = sum(1 for item in items if item.action == "conflict")
    if conflicts:
        print(t("sync.conflicts", count=conflicts))
    failed = sum(1 for item in items if item.action == "failed")
    if failed:
        print(t("sync.partial_failure", failed=failed))
        sys.exit(1)
    if not remove and not dry_run:
        print(t("sync.done"))
