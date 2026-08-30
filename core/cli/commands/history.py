"""``ca history`` command group."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from core.constants import ENGINES
from core.i18n import t

from .. import helpers as _helpers


def _history_list(ctx, engine, include_subagents=False):  # type: ignore[no-untyped-def]
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.session_history.session_finder import find_all_sessions

    project_path = str(Path.cwd())
    sessions = find_all_sessions(project_path, engine=engine)
    hidden = 0
    if not include_subagents:
        kept = [s for s in sessions if not s.parent_session_id]
        hidden = len(sessions) - len(kept)
        sessions = kept
    if not sessions:
        print(t("history.none"))
        return
    print(t("history.found", count=len(sessions), path=project_path))
    if hidden:
        print(t("history.subagents_hidden", count=hidden))
    for i, s in enumerate(sessions):
        title = s.title or s.first_user_message[:60] or t("history.no_title")
        print(
            f"  [{i + 1}] {s.engine.value:8s} | {s.started_at[:19]:19s} | {s.message_count:3d} msgs | {title}"
        )
        print(f"       ID: {s.session_id}")
    print(t("history.show_hint"))


@click.group(invoke_without_command=True)
@click.pass_context
def history(ctx):  # type: ignore[no-untyped-def]
    """Session history management."""
    if ctx.invoked_subcommand is None:
        _history_list(ctx, engine=None)


@history.command(name="list")
@click.option("--engine", default=None, help="Filter by engine")
@click.option(
    "--include-subagents",
    is_flag=True,
    help="Also list subagent runs, which belong to the session that spawned them",
)
@click.pass_context
def history_list(ctx, engine, include_subagents):  # type: ignore[no-untyped-def]
    """List all sessions for this project."""
    _history_list(ctx, engine=engine, include_subagents=include_subagents)


@history.command()
@click.argument("engine_name")
@click.argument("session_id")
@click.pass_context
def show(ctx, engine_name, session_id):  # type: ignore[no-untyped-def]
    """Show full session content."""
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.session_history.session_finder import find_session_by_id

    project_path = str(Path.cwd())
    session = find_session_by_id(session_id, engine_name, project_path)
    if not session:
        print(t("history.not_found", engine=engine_name, session_id=session_id))
        return
    print(f"{'=' * 60}")
    print(f"{t('history.field_engine')}  {session.engine.value}")
    print(f"{t('history.field_session')}  {session.session_id}")
    print(f"{t('history.field_started')}  {session.started_at}")
    print(f"{t('history.field_messages')}  {session.message_count}")
    print(f"{t('history.field_model')}  {session.model or t('history.unknown_model')}")
    print(f"{'=' * 60}\n")
    for msg in session.messages:
        role_label = (
            t("history.role_user")
            if msg.role == "user"
            else t("history.role_assistant")
        )
        print(f"[{msg.timestamp[:19] if msg.timestamp else ''}] {role_label}")
        if msg.content:
            text = msg.content if len(msg.content) <= 500 else msg.content[:500] + "..."
            print(text)
        for tc in msg.tool_calls:
            print(
                f"  * {tc.name}({tc.args_preview[:80]})"
                if tc.args_preview
                else f"  * {tc.name}"
            )
        print()


@history.command()
@click.argument("source_engine")
@click.argument("session_id")
@click.argument("target_engine")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt")
@click.pass_context
def convert(ctx, source_engine, session_id, target_engine, yes):  # type: ignore[no-untyped-def]
    """Convert session to another engine format."""
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.session_history.session_finder import find_session_by_id
    from core.session_history.writers import write_session

    project_path = str(Path.cwd())
    session = find_session_by_id(session_id, source_engine, project_path)
    if not session:
        print(t("history.not_found", engine=source_engine, session_id=session_id))
        return
    title = session.title or session.first_user_message[:60] or t("history.no_title")
    print(t("convert.about_to"))
    print(
        t(
            "convert.line_source",
            engine=source_engine,
            session_id=session_id,
            count=session.message_count,
        )
    )
    print(t("convert.line_title", title=title))
    print(t("convert.line_target", engine=target_engine))
    if not yes:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print(t("convert.needs_confirmation"))
            return
        if not click.confirm(t("convert.confirm"), default=False):
            print(t("convert.cancelled"))
            return
    try:
        new_id = write_session(session, target_engine)
        print(t("convert.done", source=source_engine, target=target_engine))
        print(t("convert.new_id", session_id=new_id))
        if target_engine in ENGINES:
            print(t(f"convert.resume_{target_engine}", session_id=new_id))
    except Exception as e:
        print(t("convert.failed", error=e))
