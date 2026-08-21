"""``ca project`` command group."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from core.i18n import t
from core.resource_locator import get_default_config_path
from core.services.config_service import ConfigService

from .. import helpers as _helpers  # noqa: F401 (kept for mirror)


@click.group(name="project", invoke_without_command=True)
@click.pass_context
def project(ctx):  # type: ignore[no-untyped-def]
    """Manage the project registry (config.json's project_registry)."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@project.command(name="add")
@click.argument("path", required=False, default=".")
@click.option("--group", default="common", show_default=True, help="Resource group to bind this project to.")
@click.pass_context
def project_add(ctx, path, group):  # type: ignore[no-untyped-def]
    root = ctx.obj["root"]
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        print(t("project.not_a_directory", path=resolved))
        sys.exit(1)
    config = ctx.obj["config"]
    if group not in config.get("groups", {}):
        print(t("project.group_missing", group=group))
    service = ConfigService(get_default_config_path(root))
    registry = service.add_project(str(resolved), group)
    print(t("project.add_ok", path=resolved, group=group))
    print(t("project.registry_size", count=len(registry)))


@project.command(name="remove")
@click.argument("path")
@click.pass_context
def project_remove(ctx, path):  # type: ignore[no-untyped-def]
    root = ctx.obj["root"]
    resolved = Path(path).expanduser().resolve()
    service = ConfigService(get_default_config_path(root))
    before = service.get_config()[0].get("project_registry", [])
    registry = service.delete_project(str(resolved))
    if len(registry) == len(before):
        print(t("project.remove_missing", path=resolved))
        sys.exit(1)
    print(t("project.removed", path=resolved))


@project.command(name="list")
@click.pass_context
def project_list(ctx):  # type: ignore[no-untyped-def]
    config = ctx.obj["config"]
    registry = config.get("project_registry", [])
    if not registry:
        print(t("project.none_registered"))
        return
    for item in registry:
        path = item.get("path", "?")
        available = path != "?" and Path(path).expanduser().is_dir()
        mark = "v" if available else t("project.missing_marker")
        print(t("project.list_row", mark=mark, path=path, group=item.get("group", "?")))
