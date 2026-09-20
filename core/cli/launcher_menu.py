"""Interactive terminal launcher console for bare ``ca`` invocations in a TTY."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click
import questionary
from questionary import Choice, Style

from core.console import configure_console_encoding
from core.engine_registry import ENGINES
from core.i18n import t
from core.session_history import repository

from . import helpers as _helpers
from .commands.resume import format_relative_time, resume_session_flow

if TYPE_CHECKING:
    pass

MENU_STYLE = Style(
    [
        ("qmark", "fg:#f59e0b bold"),
        ("question", "bold"),
        ("pointer", "fg:#3b82f6 bold"),
        ("highlighted", "fg:#3b82f6 bold"),
        ("selected", "fg:#10b981"),
        ("separator", "fg:#64748b"),
        ("instruction", "fg:#94a3b8"),
    ]
)


def print_banner(project_path: Path, latest_summary: dict | None = None) -> None:
    """Prints a clean welcome header showing current project and latest activity."""
    proj_name = project_path.name or str(project_path)
    proj_str = str(project_path)

    print()
    print("  ╭─ CodeAgent CLI ─────────────────────────────────────────────╮")
    print(f"  │  📂 {t('launcher.project_label')}: {proj_name} ({proj_str})")
    if latest_summary:
        eng = latest_summary.get("engine", "unknown")
        rel_time = format_relative_time(latest_summary.get("started_at", ""))
        msg_count = latest_summary.get("message_count", 0)
        title = latest_summary.get("title") or t("history.no_title")
        title = title.replace("\n", " ").strip()
        if len(title) > 35:
            title = title[:32] + "..."
        print(
            f"  │  💬 {t('launcher.latest_session_label')}: [{eng}] {rel_time} · {title} ({msg_count} msgs)"
        )
    print("  ╰─────────────────────────────────────────────────────────────╯")
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
        choices: list[Choice] = []

        if latest_summary:
            eng = latest_summary.get("engine", "unknown")
            rel_time = format_relative_time(latest_summary.get("started_at", ""))
            title = latest_summary.get("title") or t("history.no_title")
            title = title.replace("\n", " ").strip()
            if len(title) > 28:
                title = title[:25] + "..."
            resume_text = t(
                "launcher.resume_latest",
                engine=eng,
                time=rel_time,
                title=title,
            )
            choices.append(Choice(title=resume_text, value="resume_latest"))

        choices.extend(
            [
                Choice(title=t("launcher.launch_engine"), value="launch_engine"),
                Choice(title=t("launcher.browse_sessions"), value="browse_sessions"),
                Choice(title=t("launcher.switch_session"), value="switch_session"),
                Choice(title=t("launcher.web_ui"), value="web_ui"),
                Choice(title=t("launcher.status"), value="status"),
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
            order = ["codex", "claude", "opencode", "antigravity", "codebuddy"]
            for eng_id in order:
                spec = ENGINES.get(eng_id)
                if spec:
                    engine_choices.append(
                        Choice(
                            title=f"{spec.display_name:<18} ({spec.name})",
                            value=spec.name,
                        )
                    )
            for name, spec in ENGINES.items():
                if name not in order:
                    engine_choices.append(
                        Choice(
                            title=f"{spec.display_name:<18} ({spec.name})",
                            value=spec.name,
                        )
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
