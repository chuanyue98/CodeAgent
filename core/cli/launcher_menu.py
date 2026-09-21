"""Interactive terminal launcher console for bare ``ca`` invocations in a TTY."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import click
import questionary
from questionary import Choice, Separator

from core.console import configure_console_encoding
from core.engine_registry import ENGINES
from core.i18n import t
from core.report import display_width
from core.session_history import repository

from . import helpers as _helpers
from .commands.resume import format_relative_time, resume_session_flow
from .ui_styles import (
    CLI_QUESTIONARY_STYLE,
    StyledTitle,
    get_engine_theme,
    pad_display,
)

if TYPE_CHECKING:
    pass

MENU_STYLE = CLI_QUESTIONARY_STYLE


def print_banner(project_path: Path, latest_summary: dict | None = None) -> None:
    """Prints a clean welcome header showing current project and latest activity."""
    proj_name = project_path.name or str(project_path)
    proj_str = str(project_path)

    line1_raw = f"📂 {t('launcher.project_label')}: {proj_name}  ({proj_str})"
    line1_styled = (
        f"📂 {click.style(t('launcher.project_label') + ':', bold=True)} "
        f"{click.style(proj_name, fg='bright_cyan', bold=True)}  "
        f"{click.style('(' + proj_str + ')', fg='bright_black')}"
    )
    lines: list[tuple[str, str]] = [(line1_raw, line1_styled)]

    if latest_summary:
        eng_raw = latest_summary.get("engine", "unknown")
        theme = get_engine_theme(eng_raw)
        rel_time = format_relative_time(latest_summary.get("started_at", ""))
        msg_count = latest_summary.get("message_count", 0)
        title = latest_summary.get("title") or t("history.no_title")
        title = title.replace("\n", " ").strip()
        if len(title) > 40:
            title = title[:37] + "..."
        line2_raw = f"💬 {t('launcher.latest_session_label')}: {theme.badge} {rel_time} · {title} ({msg_count} msgs)"
        line2_styled = (
            f"💬 {click.style(t('launcher.latest_session_label') + ':', bold=True)} "
            f"{click.style(theme.badge, fg=theme.click_fg, bold=True)} "
            f"{click.style(rel_time, fg='bright_black')} "
            f"{click.style('·', fg='bright_black')} "
            f"{click.style(title, fg='bright_white')} "
            f"{click.style(f'({msg_count} msgs)', fg='bright_black')}"
        )
        lines.append((line2_raw, line2_styled))

    inner_w = max(64, max(display_width(r) for r, _ in lines) + 2)
    raw_brand = "🤖 CodeAgent CLI "
    bar_len = max(0, inner_w + 2 - display_width(raw_brand) - 2)

    border_color = "bright_blue"
    brand_styled = click.style(raw_brand, fg="bright_cyan", bold=True)
    top = f"  {click.style('╭─ ', fg=border_color)}{brand_styled}{click.style('─' * bar_len + '╮', fg=border_color)}"
    bot = f"  {click.style('╰' + '─' * (inner_w + 2) + '╯', fg=border_color)}"

    print()
    print(top)
    for raw, styled in lines:
        pad = inner_w - display_width(raw)
        print(
            f"  {click.style('│', fg=border_color)} {styled}{' ' * pad} {click.style('│', fg=border_color)}"
        )
    print(bot)
    print()


def run_interactive_launcher(ctx: click.Context) -> int:
    """Runs the interactive launcher console."""
    configure_console_encoding()
    _helpers._ensure_project_on_path(ctx.obj["root"])

    project_path = Path.cwd().resolve()
    latest_summary: dict | None = None
    try:
        summaries = repository.list_summaries(
            project=str(project_path), limit=1, include_subagents=False
        )
        if summaries:
            latest_summary = summaries[0]
    except Exception:
        latest_summary = None

    print_banner(project_path, latest_summary)

    while True:
        choices: list[Choice | Separator] = []

        if latest_summary:
            eng = latest_summary.get("engine", "unknown")
            theme = get_engine_theme(eng)
            rel_time = format_relative_time(latest_summary.get("started_at", ""))
            title = latest_summary.get("title") or t("history.no_title")
            title = title.replace("\n", " ").strip()
            if len(title) > 28:
                title = title[:25] + "..."
            resume_plain = t(
                "launcher.resume_latest",
                engine=eng,
                time=rel_time,
                title=title,
            )
            resume_tokens = [
                ("class:instruction", "↩  "),
                ("class:text", f"{t('launcher.latest_session_label')}: "),
                (f"class:{theme.style_class}", f"{theme.badge} "),
                ("class:time", f"{rel_time} "),
                ("class:dim", "· "),
                ("class:session_title", f"{title}"),
            ]
            choices.append(
                Choice(
                    title=StyledTitle(resume_tokens, resume_plain),
                    value="resume_latest",
                )
            )

        choices.append(Separator(f"── {t('launcher.group_sessions')} ──"))
        choices.extend(
            [
                Choice(title=t("launcher.launch_engine"), value="launch_engine"),
                Choice(title=t("launcher.browse_sessions"), value="browse_sessions"),
                Choice(title=t("launcher.switch_session"), value="switch_session"),
            ]
        )

        choices.append(Separator(f"── {t('launcher.group_tools')} ──"))
        choices.extend(
            [
                Choice(title=t("launcher.web_ui"), value="web_ui"),
                Choice(title=t("launcher.status"), value="status"),
            ]
        )

        choices.append(Separator(f"── {t('launcher.group_manage')} ──"))
        choices.extend(
            [
                Choice(title=t("launcher.more"), value="more"),
                Choice(title=t("launcher.exit"), value="exit"),
            ]
        )

        try:
            action = questionary.select(
                t("launcher.select_action"),
                choices=choices,
                style=MENU_STYLE,
            ).ask()
        except Exception:
            click.echo(ctx.get_help())
            return 0

        if action is None or action == "exit":
            print(t("cli.cancelled"))
            return 0

        if action == "resume_latest":
            return resume_session_flow(ctx, selector="1")

        if action == "browse_sessions":
            return resume_session_flow(ctx, selector="")

        if action == "switch_session":
            from .commands.switch import switch

            return ctx.invoke(switch)

        if action == "web_ui":
            from .commands.tasks import ui

            return ctx.invoke(ui)

        if action == "status":
            from .commands.status import status

            return ctx.invoke(status)

        if action == "launch_engine":
            engine_choices: list[Choice] = []
            order = ["claude", "codex", "opencode", "antigravity", "codebuddy"]
            for eng_id in order:
                spec = ENGINES.get(eng_id)
                if spec:
                    installed = any(shutil.which(cmd) for cmd in spec.cli_candidates)
                    badge = (
                        t("launcher.engine_ready")
                        if installed
                        else t("launcher.engine_missing")
                    )
                    badge_class = (
                        "class:badge_ready" if installed else "class:badge_missing"
                    )
                    theme = get_engine_theme(eng_id)
                    name_padded = pad_display(spec.display_name, 18)
                    plain = f"{name_padded} {badge}"
                    tokens = [
                        (f"class:{theme.style_class}", name_padded + " "),
                        (badge_class, badge),
                    ]
                    engine_choices.append(
                        Choice(title=StyledTitle(tokens, plain), value=spec.name)
                    )
            for name, spec in ENGINES.items():
                if name not in order:
                    installed = any(shutil.which(cmd) for cmd in spec.cli_candidates)
                    badge = (
                        t("launcher.engine_ready")
                        if installed
                        else t("launcher.engine_missing")
                    )
                    badge_class = (
                        "class:badge_ready" if installed else "class:badge_missing"
                    )
                    theme = get_engine_theme(name)
                    name_padded = pad_display(spec.display_name, 18)
                    plain = f"{name_padded} {badge}"
                    tokens = [
                        (f"class:{theme.style_class}", name_padded + " "),
                        (badge_class, badge),
                    ]
                    engine_choices.append(
                        Choice(title=StyledTitle(tokens, plain), value=spec.name)
                    )
            engine_choices.append(Choice(title=t("launcher.back"), value="back"))

            try:
                chosen_engine = questionary.select(
                    t("launcher.select_engine"),
                    choices=engine_choices,
                    style=MENU_STYLE,
                ).ask()
            except Exception:
                chosen_engine = None

            if not chosen_engine or chosen_engine == "back":
                continue

            return _helpers._launch_engine(ctx, [chosen_engine])

        if action == "more":
            more_choices = [
                Choice(title=t("launcher.sync"), value="sync"),
                Choice(title=t("launcher.mcp_install"), value="mcp_install"),
                Choice(title=t("launcher.doctor"), value="doctor"),
                Choice(title=t("launcher.help"), value="help"),
                Choice(title=t("launcher.back"), value="back"),
            ]
            try:
                chosen_more = questionary.select(
                    t("launcher.select_action"),
                    choices=more_choices,
                    style=MENU_STYLE,
                ).ask()
            except Exception:
                chosen_more = None

            if not chosen_more or chosen_more == "back":
                continue

            if chosen_more == "sync":
                from .commands.sync import sync

                return ctx.invoke(sync)

            if chosen_more == "mcp_install":
                from .commands.mcp import mcp_install

                return ctx.invoke(mcp_install)

            if chosen_more == "doctor":
                from .commands.tasks import doctor

                return ctx.invoke(doctor)

            if chosen_more == "help":
                click.echo(ctx.get_help())
                return 0

    return 0
