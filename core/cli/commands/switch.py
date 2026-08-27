"""``ca switch`` -- carry the conversation you are in to another engine.

The product's whole premise is that a conversation outlives the tool it
started in, but until now the CLI could only take you half way: ``ca history
convert`` wrote the target engine's file and then printed a second command
for you to run yourself. This closes that loop in one step, the way the Web
UI's convert-and-launch already does.

Conversion is additive -- the source session is left on disk untouched -- so
this does not prompt for confirmation the way ``ca history convert`` does.
There the arguments are opaque ids where a typo silently picks the wrong
session; here the target engine is named explicitly and the source is
whatever you were just working in.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from core.constants import ENGINES
from core.i18n import t

from .. import helpers as _helpers
from ..session_select import SessionSelectorError, resolve_session


@click.command()
@click.argument("target_engine")
@click.argument("selector", required=False)
@click.option(
    "--engine",
    "source_engine",
    default=None,
    help="Only consider sessions from this engine when picking the source.",
)
@click.option(
    "--no-launch",
    is_flag=True,
    help="Convert and print the resume command, but do not start the engine.",
)
@click.pass_context
def switch(ctx, target_engine, selector, source_engine, no_launch):  # type: ignore[no-untyped-def]
    """Continue a session in TARGET_ENGINE.

    SELECTOR is the number `ca history` printed, or a session id. Omit it to
    take the most recent session in this project.
    """
    target_engine = target_engine.lower()
    if target_engine not in ENGINES:
        print(t("switch.unknown_engine", engine=target_engine))
        print(t("switch.known_engines", engines=", ".join(sorted(ENGINES))))
        return 1

    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.services.resume_commands import resume_command
    from core.session_history.writers import write_session

    project_path = str(Path.cwd())
    try:
        session = resolve_session(selector, project_path, engine=source_engine)
    except SessionSelectorError as exc:
        print(t(exc.message_key, **exc.fields))
        return 1

    title = session.title or session.first_user_message[:60] or t("history.no_title")
    source = session.engine.value

    if source == target_engine:
        # Already native. Converting would fork a second copy of the same
        # conversation into the same engine, so this just resumes it.
        print(t("switch.already_native", engine=target_engine, title=title))
        session_id = session.session_id
    else:
        print(
            t(
                "switch.converting",
                source=source,
                target=target_engine,
                count=session.message_count,
                title=title,
            )
        )
        try:
            session_id = write_session(session, target_engine)
        except Exception as exc:
            print(t("convert.failed", error=exc))
            return 1
        print(t("convert.new_id", session_id=session_id))

    try:
        argv = resume_command(target_engine, session_id, Path(project_path))
    except ValueError as exc:
        print(t("switch.no_resume_command", error=exc))
        return 1

    if no_launch:
        print(t("switch.resume_manually", command=" ".join(argv)))
        return 0

    print(t("switch.launching", engine=target_engine))
    try:
        return subprocess.run(
            argv, cwd=project_path, env=ctx.obj.get("child_env")
        ).returncode
    except FileNotFoundError:
        # The conversion already succeeded, so the session is waiting for them
        # once the CLI is on PATH -- say so rather than looking like a failure.
        print(t("switch.engine_not_installed", engine=target_engine))
        print(t("switch.resume_manually", command=" ".join(argv)))
        return 1
