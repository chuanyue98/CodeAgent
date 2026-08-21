"""``ca resources`` command group."""

from __future__ import annotations

import click

from core.i18n import t
from core.resource_locator import get_default_config_path

from .. import helpers as _helpers

_RESOURCE_KINDS = ("skills", "plugins", "hooks", "prompts")


@click.group(name="resources", invoke_without_command=True)
@click.pass_context
def resources(ctx):  # type: ignore[no-untyped-def]
    """Discover skills, plugins, hooks, and prompts without opening the Web UI."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@resources.command(name="list")
@click.argument("kind", type=click.Choice(_RESOURCE_KINDS))
@click.option("--group", default="codeagent", show_default=True, help="Resource group to check the enabled/active state against.")
@click.pass_context
def resources_list(ctx, kind, group):  # type: ignore[no-untyped-def]
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.web.resource_paths import ROOT_DIR, resolve_resource_path

    config = ctx.obj["config"]
    enabled_ids = set(config.get("groups", {}).get(group, {}).get(kind, []))
    rows: list[tuple[str, str, bool]] = []
    if kind == "skills":
        from core.services.skill_service import SkillService

        skill_service = SkillService(resolve_resource_path("skills", "CA_SKILLS_ROOT"))
        for items in skill_service.get_detailed_skills().values():
            for item in items:
                rows.append((item["id"], item["description"], item["id"] in enabled_ids))
    elif kind == "plugins":
        from core.services.plugin_service import PluginService

        plugin_service = PluginService(resolve_resource_path("plugins", "CA_PLUGINS_ROOT"))
        for items in plugin_service.get_detailed_plugins().values():
            for item in items:
                rows.append((item["id"], item["description"], item["id"] in enabled_ids))
    elif kind == "hooks":
        from core.services.hook_service import HookService

        hook_service = HookService(resolve_resource_path("hooks", "CA_HOOKS_ROOT"), get_default_config_path(ctx.obj["root"]))
        for item in hook_service.get_detailed_hooks():
            rows.append((item["id"], item["description"] or item["event"], item["isActive"]))
    else:  # prompts
        from core.services.prompt_service import PromptService

        prompt_service = PromptService(resolve_resource_path("prompt", "CA_PROMPTS_ROOT"), ROOT_DIR)
        for item in prompt_service.get_prompt_groups():
            rows.append((item["id"], item["description"], item["id"] in enabled_ids))
    if not rows:
        print(t("resources.none", kind=kind))
        return
    label = t("resources.label_active") if kind == "hooks" else t("resources.label_enabled_in", group=group)
    click.echo(click.style(t("resources.header", kind=kind.capitalize(), count=len(rows), label=label), bold=True))
    for resource_id, description, enabled in sorted(rows):
        mark = click.style("●", fg="green") if enabled else click.style("○", fg="bright_black")
        desc = f" — {description}" if description else ""
        click.echo(f"  {mark} {resource_id}{desc}")
