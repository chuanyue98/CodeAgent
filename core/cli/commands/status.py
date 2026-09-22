"""``ca status`` — 一屏说清这套体系现在正在为你做什么。

``ca doctor`` 回答"环境是否健康"（依赖在不在、配置能不能解析、有没有残留注入），
这个命令回答的是一个不同的问题："此刻驱动我的规则、资源和引擎分别是什么状态"。
两者的检查项刻意不重叠。

因此这里只读配置与引擎注册表，**不实例化引擎、不跑 scanner**——它是随时随地
可以敲一下的命令，不该因为解析资源而变慢。资源解析得对不对，是 doctor 的事。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click

from core.config_manager import ConfigManager
from core.engine_registry import ENGINES, EngineSpec
from core.i18n import t
from core.project_groups import resolve_project_group
from core.report import INFO, OK, WARN, Section, display_width, render_sections

_RESOURCE_KINDS = (
    ("skills", "status.kind_skills"),
    ("prompts", "status.kind_prompts"),
    ("hooks", "status.kind_hooks"),
    ("plugins", "status.kind_plugins"),
)


def _engine_cli_path(spec: EngineSpec) -> str | None:
    """引擎 CLI 的可执行文件路径，不在 PATH 上时返回 None。

    与 ``core/doctor.check_engines`` 同一套候选与后缀规则：POSIX 上跳过
    ``.cmd``/``.bat``/``.exe``，因为那些候选只对 Windows 有意义。
    """
    is_windows = sys.platform == "win32"
    for name in spec.cli_candidates:
        if not is_windows and name.lower().endswith((".cmd", ".bat", ".exe")):
            continue
        found = shutil.which(name)
        if found:
            return found
    return None


def _project_section(config: dict, group: str) -> Section:
    section = Section(t("status.section_project"))
    cwd = Path.cwd()

    section.add(INFO, t("status.label_cwd"), detail=str(cwd))

    # 登记与否要单独看：没有登记时 cwd 会落到默认组，那不是用户选的组，
    # 报出来才能解释"为什么我的资源配置没生效"。
    registered = resolve_project_group(cwd, config.get("project_registry"))
    if registered:
        section.add(OK, t("status.label_group"), detail=group)
    else:
        section.add(
            WARN,
            t("status.label_group"),
            detail=t("status.group_unregistered", group=group),
            fix_hint=t("status.group_register_hint"),
        )

    section.add(
        INFO,
        t("status.label_projects"),
        detail=t(
            "status.projects_count", count=len(config.get("project_registry") or [])
        ),
    )

    return section


def _resources_section(config: dict, group: str) -> Section:
    section = Section(t("status.section_resources", group=group))
    declared = config.get("groups", {}).get(group)
    if not isinstance(declared, dict):
        section.add(WARN, t("status.group_missing", group=group))
        return section

    for kind, kind_key in _RESOURCE_KINDS:
        names = [str(name) for name in declared.get(kind) or []]
        section.add(
            OK if names else INFO,
            t("status.resource_count", kind=t(kind_key), count=len(names)),
            detail=", ".join(names),
        )
    return section


def _engines_section() -> Section:
    section = Section(t("status.section_engines"))

    for spec in ENGINES.values():
        cli_path = _engine_cli_path(spec)
        if cli_path is None:
            section.add(
                WARN,
                spec.display_name,
                detail=t("status.engine_missing"),
                fix_hint=spec.install_hint,
            )
        else:
            section.add(OK, spec.display_name, detail=cli_path)
    return section


@click.command(name="status", help=t("cli.desc.status"))
@click.pass_context
def status(ctx):  # type: ignore[no-untyped-def]
    config = ctx.obj["config"]

    # 用已加载的那份配置，避免二次读盘；ConfigManager 只借用它的组解析逻辑
    # （与 doctor 的 _LightweightResolver 同一做法）。
    manager = ConfigManager(ctx.obj["root"])
    manager.full_config = config
    group = manager.get_current_project_group()

    sections = [
        _project_section(config, group),
        _resources_section(config, group),
        _engines_section(),
    ]

    click.echo()
    title = t("status.title")
    click.echo(click.style(f"  {title}", bold=True))
    click.echo("  " + "=" * display_width(title))
    render_sections(sections)
    click.echo()
