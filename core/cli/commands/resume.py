"""``ca resume`` (and ``ca -r``) -- resume a session across any engine.

Just like ``claude -r`` lets you pick from recent sessions interactively,
``ca -r`` / ``ca resume`` provides a unified, cross-engine session resume
experience for the current project.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import click

from core.constants import normalize_engine_name
from core.i18n import t

from .. import helpers as _helpers
from ..ui_styles import (
    CLI_QUESTIONARY_STYLE,
    format_styled_session_choice,
    get_engine_theme,
    pad_display,
    truncate_display,
)

#: 交互列表里最多展示多少条"最近会话"。编号解析用的却是全量列表——与
#: ``ca history`` / ``ca -s`` 同一口径——所以 ``ca -r 25`` 和 ``ca -s 25``
#: 指向同一个会话，而屏幕上不必铺开几十条。
DISPLAY_LIMIT = 20


def format_relative_time(ts_str: str) -> str:
    """Formats an ISO timestamp into a localized human-readable relative time string."""
    if not ts_str:
        return "-"
    try:
        clean_ts = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
            now = datetime.now(UTC)
        else:
            now = datetime.now(dt.tzinfo)
        diff = now - dt
        secs = max(0, int(diff.total_seconds()))
        if secs < 60:
            return t("time.just_now")
        elif secs < 3600:
            return t("time.minutes_ago", minutes=max(1, secs // 60))
        elif secs < 86400:
            return t("time.hours_ago", hours=max(1, secs // 3600))
        elif secs < 86400 * 2:
            return t("time.yesterday")
        elif secs < 86400 * 30:
            return t("time.days_ago", days=max(1, secs // 86400))
        else:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        return ts_str[:10]


def format_session_choice_title(idx: int, s: dict) -> str:
    """Formats a session row with aligned columns and distinct engine badges."""
    eng_raw = s.get("engine", "unknown")
    theme = get_engine_theme(eng_raw)
    eng_padded = pad_display(theme.badge, 14)

    time_str = format_relative_time(s.get("started_at", ""))
    time_padded = pad_display(time_str, 12)

    msg_count = s.get("message_count", 0)
    msg_str = f"{msg_count:3d} msgs"

    title = s.get("title") or t("history.no_title")
    title = truncate_display(title.replace("\n", " ").strip(), 50)

    return f"[{idx:2d}]  {eng_padded} {time_padded} · {msg_str}  │ {title}"


def resume_session_flow(
    ctx: click.Context,
    selector: str | None = None,
    engine: str | None = None,
) -> int:
    """Core logic to select and resume a session."""
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.services.resume_commands import resume_command
    from core.session_history import repository

    _helpers.warm_session_index()

    if engine:
        engine = normalize_engine_name(engine)

    project_path = str(Path.cwd())

    # Empty string (passed when invoked as bare `ca -r`) means interactive mode
    if selector == "":
        selector = None

    # Full list for resolution, matching ``ca history`` / ``ca -s``: a number
    # must name the same session in every entry point. The picker below shows
    # only the most recent DISPLAY_LIMIT.
    all_summaries = repository.list_summaries(
        project=project_path,
        engine=engine,
        include_subagents=False,
        limit=100000,
    )

    if not all_summaries:
        print(t("resume.no_sessions", path=project_path))
        return 1

    summaries = all_summaries[:DISPLAY_LIMIT]

    def _print_list() -> None:
        print(t("resume.title", path=project_path, count=len(all_summaries)))
        for i, s in enumerate(summaries, 1):
            print(f"  {format_session_choice_title(i, s)}")
        if len(all_summaries) > len(summaries):
            print(t("resume.more", shown=len(summaries), count=len(all_summaries)))

    chosen_summary: dict | None = None

    if selector is not None:
        try:
            idx = int(selector)
            if 1 <= idx <= len(all_summaries):
                chosen_summary = all_summaries[idx - 1]
            else:
                print(t("resume.invalid_index", index=idx, count=len(all_summaries)))
                return 1
        except ValueError:
            for s in all_summaries:
                if s["session_id"] == selector:
                    chosen_summary = s
                    break
            if chosen_summary is None:
                print(t("resume.not_found", selector=selector))
                return 1
    else:
        if not sys.stdin.isatty():
            _print_list()
            chosen_summary = summaries[0]
        else:
            used_questionary = False
            try:
                import questionary
                from questionary import Choice

                choices: list[Choice] = []
                for i, s in enumerate(summaries, 1):
                    rel_time = format_relative_time(s.get("started_at", ""))
                    choices.append(
                        Choice(
                            title=format_styled_session_choice(i, s, rel_time),
                            value=s,
                        )
                    )
                choices.append(Choice(title=t("launcher.exit"), value="exit"))

                selected = questionary.select(
                    t("resume.select_prompt"),
                    choices=choices,
                    style=CLI_QUESTIONARY_STYLE,
                ).ask()

                if selected is None or selected == "exit":
                    print(t("cli.cancelled"))
                    return 0
                chosen_summary = selected
                used_questionary = True
            except Exception:
                used_questionary = False

            if not used_questionary:
                _print_list()

                prompt_text = t("resume.prompt", count=len(summaries))
                try:
                    raw = input(f"\n{prompt_text} ").strip()
                except (KeyboardInterrupt, EOFError):
                    print()
                    return 0

                if not raw:
                    chosen_summary = summaries[0]
                elif raw.lower() in ("q", "quit", "exit"):
                    return 0
                else:
                    try:
                        choice_idx = int(raw)
                        if 1 <= choice_idx <= len(summaries):
                            chosen_summary = summaries[choice_idx - 1]
                        else:
                            print(
                                t(
                                    "resume.invalid_index",
                                    index=choice_idx,
                                    count=len(summaries),
                                )
                            )
                            return 1
                    except ValueError:
                        print(
                            t(
                                "resume.invalid_choice",
                                input=raw,
                                count=len(summaries),
                            )
                        )
                        return 1

    if chosen_summary is None:
        return 0

    target_engine = chosen_summary["engine"]
    session_id = chosen_summary["session_id"]
    title = chosen_summary.get("title") or t("history.no_title")

    print(t("resume.launching", engine=target_engine, title=title))

    try:
        argv = resume_command(target_engine, session_id, Path(project_path))
    except ValueError as exc:
        print(t("resume.no_resume_command", error=exc))
        return 1

    return _helpers.run_resume_command(
        argv,
        target_engine,
        project_path=project_path,
        child_env=ctx.obj.get("child_env"),
        not_installed_msg_key="switch.engine_not_installed",
        manual_msg_key="switch.resume_manually",
        runner=subprocess.run,
        which=shutil.which,
    )


@click.command(name="resume", help=t("cli.desc.resume_cmd"))
@click.argument("selector", required=False, default=None)
@click.option(
    "--engine", "-e", "engine", default=None, help=t("cli.help.resume_cmd_engine")
)
@click.pass_context
def resume(ctx, selector, engine):  # type: ignore[no-untyped-def]
    return resume_session_flow(ctx, selector=selector, engine=engine)
