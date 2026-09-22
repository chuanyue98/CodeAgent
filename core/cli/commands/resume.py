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
from core.engine_registry import ENGINES
from core.i18n import t

from .. import helpers as _helpers
from ..ui_styles import (
    CLI_QUESTIONARY_STYLE,
    ENGINE_THEMES,
    format_styled_session_choice,
    get_engine_theme,
    pad_display,
)

ENGINE_BADGES: dict[str, str] = {k: v.badge for k, v in ENGINE_THEMES.items()}
_pad_display = pad_display


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
        secs = int(diff.total_seconds())
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
    title = title.replace("\n", " ").strip()
    if len(title) > 50:
        title = title[:47] + "..."

    return f"[{idx:2d}]  {eng_padded} {time_padded} · {msg_str}  │ {title}"


def resume_session_flow(
    ctx: click.Context,
    selector: str | None = None,
    engine: str | None = None,
    no_launch: bool = False,
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

    summaries = repository.list_summaries(
        project=project_path,
        engine=engine,
        include_subagents=False,
        limit=20,
    )

    if not summaries:
        print(t("resume.no_sessions", path=project_path))
        return 1

    chosen_summary: dict | None = None

    if selector is not None:
        try:
            idx = int(selector)
            if 1 <= idx <= len(summaries):
                chosen_summary = summaries[idx - 1]
            else:
                print(t("resume.invalid_index", index=idx, count=len(summaries)))
                return 1
        except ValueError:
            for s in summaries:
                if s["session_id"] == selector:
                    chosen_summary = s
                    break
            if chosen_summary is None:
                print(t("resume.not_found", selector=selector))
                return 1
    else:
        if not sys.stdin.isatty():
            print(t("resume.title", path=project_path, count=len(summaries)))
            for i, s in enumerate(summaries, 1):
                print(f"  {format_session_choice_title(i, s)}")
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
                print(t("resume.title", path=project_path, count=len(summaries)))
                for i, s in enumerate(summaries, 1):
                    print(f"  {format_session_choice_title(i, s)}")

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

    if no_launch:
        print(t("resume.command_preview", command=" ".join(argv)))
        return 0

    try:
        return subprocess.run(
            argv, cwd=project_path, env=ctx.obj.get("child_env")
        ).returncode
    except FileNotFoundError:
        if sys.platform == "win32":
            candidates = [argv[0]]
            spec = ENGINES.get(target_engine)
            if spec:
                for c in spec.cli_candidates:
                    if c not in candidates:
                        candidates.append(c)
            for cand in candidates:
                resolved = shutil.which(cand)
                if resolved:
                    try:
                        return subprocess.run(
                            [resolved, *argv[1:]],
                            cwd=project_path,
                            env=ctx.obj.get("child_env"),
                        ).returncode
                    except FileNotFoundError:
                        continue
        print(t("switch.engine_not_installed", engine=target_engine))
        print(t("switch.resume_manually", command=" ".join(argv)))
        return 1


@click.command(name="resume")
@click.argument("selector", required=False, default=None)
@click.option("--engine", "-e", "engine", default=None, help="Filter by engine")
@click.option(
    "--no-launch",
    is_flag=True,
    help="Print the resume command, but do not start the engine.",
)
@click.pass_context
def resume(ctx, selector, engine, no_launch):  # type: ignore[no-untyped-def]
    """Resume a previous session from this project across any engine.

    SELECTOR is an index (1, 2, ...) or session id. Omit it to see an
    interactive list of recent sessions, or press Enter to resume the most recent.
    """
    return resume_session_flow(
        ctx, selector=selector, engine=engine, no_launch=no_launch
    )
