"""``ca switch`` (and ``ca -s``) -- carry the conversation you are in to another engine.

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

import shutil
import subprocess
import sys
from pathlib import Path

import click

from core.constants import ENGINES, normalize_engine_name
from core.engine_registry import ENGINES as ENGINE_SPECS
from core.i18n import t

from .. import helpers as _helpers
from ..session_select import SessionSelectorError, resolve_session
from .resume import format_relative_time


@click.command()
@click.argument("target_engine", required=False, default=None)
@click.argument("selector", required=False, default=None)
@click.option(
    "--engine",
    "source_engine",
    default=None,
    help="Only consider sessions from this engine when picking the source.",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    default=False,
    help="Confirm the latest session without interactive prompt.",
)
@click.option(
    "--no-launch",
    is_flag=True,
    help="Convert and print the resume command, but do not start the engine.",
)
@click.pass_context
def switch(ctx, target_engine, selector, source_engine, yes, no_launch):  # type: ignore[no-untyped-def]
    """Continue a session in TARGET_ENGINE (shorthand: `ca -s`).

    SELECTOR is the number `ca history` printed, or a session id. Omit it to
    take the most recent session in this project.
    """
    if target_engine is not None:
        target_engine = normalize_engine_name(target_engine)
        if target_engine not in ENGINES:
            print(t("switch.unknown_engine", engine=target_engine))
            print(t("switch.known_engines", engines=", ".join(sorted(ENGINES))))
            return 1

    if source_engine:
        source_engine = normalize_engine_name(source_engine)

    # 非交互模式缺少 target_engine 属于参数错误，必须在读取会话之前报出来。
    # 否则在没有会话历史的环境（CI / 新机器 / 容器）里会被 "No sessions found"
    # 掩盖，用户看到的提示与实际原因不符。
    if target_engine is None and not sys.stdin.isatty():
        print(t("switch.missing_target"))
        print(t("switch.known_engines", engines=", ".join(sorted(ENGINES))))
        return 1

    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.services.resume_commands import resume_command
    from core.session_history import repository
    from core.session_history.writers import write_session

    project_path = str(Path.cwd())

    session = None
    if selector is not None:
        try:
            session = resolve_session(selector, project_path, engine=source_engine)
        except SessionSelectorError as exc:
            print(t(exc.message_key, **exc.fields))
            return 1
    elif not sys.stdin.isatty() or yes:
        try:
            session = resolve_session(None, project_path, engine=source_engine)
        except SessionSelectorError as exc:
            print(t(exc.message_key, **exc.fields))
            return 1
    else:
        # Interactive mode without explicit selector: show candidate sessions preview
        summaries = repository.list_summaries(
            project=project_path,
            engine=source_engine,
            include_subagents=True,
            limit=5,
        )
        if not summaries:
            print(t("select.no_sessions", path=project_path))
            return 1

        if target_engine:
            print(t("switch.candidate_title_with_target", target=target_engine))
        else:
            print(t("switch.candidate_title"))

        default_marker = t("switch.default_marker")
        for i, s in enumerate(summaries, 1):
            eng = s.get("engine", "unknown")
            time_str = format_relative_time(s.get("started_at", ""))
            msg_count = s.get("message_count", 0)
            title = (
                s.get("title") or s.get("first_user_message") or t("history.no_title")
            )
            title = title.replace("\n", " ").strip()
            if len(title) > 55:
                title = title[:52] + "..."
            marker = f"{default_marker:<8s}" if i == 1 else "        "
            print(
                f"  [{i:2d}] {marker} [{eng:<10s}]  {time_str:<8s}  ·  {msg_count:3d} msgs  |  {title}"
            )

        if target_engine:
            prompt_text = t(
                "switch.prompt_source", target=target_engine, count=len(summaries)
            )
        else:
            prompt_text = t("switch.prompt_source_no_target", count=len(summaries))

        try:
            raw = input(f"\n{prompt_text} ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0

        chosen_summary = None
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
                            "select.index_out_of_range",
                            index=choice_idx,
                            count=len(summaries),
                        )
                    )
                    return 1
            except ValueError:
                for s in summaries:
                    if s["session_id"] == raw:
                        chosen_summary = s
                        break
                if chosen_summary is None:
                    print(t("select.not_found", selector=raw))
                    return 1

        session = repository.get_full(
            chosen_summary["engine"], chosen_summary["session_id"], project_path
        )
        if session is None:
            print(t("select.not_found", selector=chosen_summary["session_id"]))
            return 1

    source = session.engine.value

    # If target_engine was not specified in arguments: we can only be
    # interactive here (the non-interactive case returned earlier), so ask.
    if target_engine is None:
        target_candidates: list[str] = [
            e
            for e in ("codex", "claude", "opencode", "antigravity", "codebuddy")
            if e in ENGINES and e != source
        ]
        for e in sorted(ENGINES):
            if e not in target_candidates and e != source:
                target_candidates.append(e)

        if not target_candidates:
            target_candidates = [e for e in sorted(ENGINES) if e != source]

        print(f"\n{t('switch.target_engine_title')}")
        for idx, eng_name in enumerate(target_candidates, 1):
            alias_hint = " (agy)" if eng_name == "antigravity" else ""
            print(f"  [{idx:2d}] {eng_name}{alias_hint}")

        target_prompt = t("switch.prompt_target", count=len(target_candidates))
        try:
            raw_target = input(f"\n{target_prompt} ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0

        if not raw_target or raw_target.lower() in ("q", "quit", "exit"):
            return 0

        try:
            t_idx = int(raw_target)
            if 1 <= t_idx <= len(target_candidates):
                target_engine = target_candidates[t_idx - 1]
            else:
                print(t("switch.unknown_engine", engine=raw_target))
                return 1
        except ValueError:
            target_engine = normalize_engine_name(raw_target)
            if target_engine not in ENGINES:
                print(t("switch.unknown_engine", engine=raw_target))
                print(t("switch.known_engines", engines=", ".join(sorted(ENGINES))))
                return 1

    title = session.title or session.first_user_message[:60] or t("history.no_title")

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
        if sys.platform == "win32":
            candidates = [argv[0]]
            spec = ENGINE_SPECS.get(target_engine)
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
        # The conversion already succeeded, so the session is waiting for them
        # once the CLI is on PATH -- say so rather than looking like a failure.
        print(t("switch.engine_not_installed", engine=target_engine))
        print(t("switch.resume_manually", command=" ".join(argv)))
        return 1
