"""``ca ps / stop / batch-run / new`` commands."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click

from core.i18n import t

from .. import helpers as _helpers


@click.command()
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Include completed/failed/stopped runs, not just running ones",
)
@click.pass_context
def ps(ctx, show_all):  # type: ignore[no-untyped-def]
    _helpers._ensure_project_on_path(ctx.obj["root"])
    runner = _helpers._get_task_runner(ctx.obj["root"])
    runs = runner.list_runs()
    if not show_all:
        runs = [r for r in runs if r.status == "running"]
    if not runs:
        print(t("ps.none_tracked") if show_all else t("ps.none_running"))
        return
    runs.sort(key=lambda r: r.start_time, reverse=True)
    print(f"{'TASK ID':38s} {'ENGINE':9s} {'STATUS':10s} {'PID':8s} WORKSPACE")
    for r in runs:
        pid_str = str(r.pid) if r.pid else "-"
        workspace = r.workspace or "-"
        print(f"{r.task_id:38s} {r.engine:9s} {r.status:10s} {pid_str:8s} {workspace}")
    if not show_all:
        print(t("ps.hint"))


@click.command()
@click.argument("task_id")
@click.pass_context
def stop(ctx, task_id):  # type: ignore[no-untyped-def]
    _helpers._ensure_project_on_path(ctx.obj["root"])
    runner = _helpers._get_task_runner(ctx.obj["root"])
    status = runner.get_status(task_id)
    if status is None:
        print(t("stop.not_found", task_id=task_id))
        print(t("stop.list_hint"))
        sys.exit(1)
    if status.status != "running":
        print(t("stop.not_running", task_id=task_id, status=status.status))
        return
    if runner.stop_task(task_id):
        print(t("stop.stopped", task_id=task_id))
    else:
        print(t("stop.failed", task_id=task_id))
        sys.exit(1)


@click.command(name="batch-run")
@click.argument("task_name")
@click.option(
    "--engine",
    required=True,
    type=click.Choice(["claude", "opencode", "codex", "codebuddy"]),
    help="Engine to run the task with in every target project.",
)
@click.option(
    "--group",
    default=None,
    help="Only target projects registered under this resource group (default: all registered projects).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="List the projects that would run, without starting anything.",
)
@click.pass_context
def batch_run(ctx, task_name, engine, group, dry_run):  # type: ignore[no-untyped-def]
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.services.runner_service import TaskAlreadyRunningError
    from core.services.task_service import TaskService
    from core.web.resource_paths import resolve_resource_path

    config = ctx.obj["config"]
    registry = [
        item
        for item in config.get("project_registry", [])
        if isinstance(item, dict) and item.get("path")
    ]
    targets = [item for item in registry if group is None or item.get("group") == group]
    if not targets:
        scope = t("batch.scope_group", group=group) if group else ""
        print(t("batch.no_projects", scope=scope))
        sys.exit(1)
    tasks_root = resolve_resource_path("tasks", "CA_TASKS_ROOT")
    if TaskService(tasks_root).get_task(task_name) is None:
        print(t("batch.no_task", task=task_name, root=tasks_root))
        sys.exit(1)
    print(t("batch.plan_header", count=len(targets), task=task_name, engine=engine))
    for target in targets:
        print(t("batch.plan_row", path=target["path"], group=target.get("group", "?")))
    if dry_run:
        print(t("batch.dry_run"))
        return
    runner = _helpers._get_task_runner(ctx.obj["root"])
    started: list[tuple[str, str]] = []
    skipped: list[str] = []
    failed: list[tuple[str, str]] = []
    for target in targets:
        workspace = target["path"]
        proj_group = target.get("group") or "common"
        try:
            status = runner.run_task(
                task_name,
                engine,
                proj_group,
                tasks_root=tasks_root,
                workspace=workspace,
                prevent_overlap=True,
            )
        except TaskAlreadyRunningError:
            skipped.append(workspace)
            continue
        except ValueError as e:
            failed.append((workspace, str(e)))
            continue
        if status.status == "running":
            started.append((workspace, status.task_id))
        else:
            failed.append((workspace, status.status))
    print()
    for workspace, task_id in started:
        print(t("batch.started_row", task_id=task_id, workspace=workspace))
    for workspace in skipped:
        print(t("batch.skipped_row", workspace=workspace))
    for workspace, reason in failed:
        print(t("batch.failed_row", reason=reason, workspace=workspace))
    print(
        t(
            "batch.summary",
            started=len(started),
            skipped=len(skipped),
            failed=len(failed),
        )
    )
    if started:
        print(t("batch.track_hint"))
    if failed:
        sys.exit(1)


@click.command()
@click.argument("name", required=False)
@click.pass_context
def new(ctx, name):  # type: ignore[no-untyped-def]
    config = ctx.obj["config"]
    root = ctx.obj["root"]
    child_env = ctx.obj["child_env"]
    task_name = name or "unnamed_task"
    paths_cfg = config.get("paths", {})
    res_root = paths_cfg.get("resource_root")
    if res_root:
        tasks_dir = Path(res_root.replace("$CODEAGENT", str(root.as_posix()))) / "tasks"
    else:
        tasks_dir = Path(paths_cfg.get("tasks", "tasks"))
    if not tasks_dir.is_absolute():
        tasks_dir = root / tasks_dir
    try:
        rel_tasks_path = os.path.relpath(tasks_dir, Path.cwd())
    except ValueError:
        rel_tasks_path = str(tasks_dir)
    target_file = os.path.join(rel_tasks_path, f"{task_name}.md").replace("\\", "/")
    engine_script = str(root / "engines" / "start_opencode.py")
    print(t("task.authoring_start", name=task_name))
    print(t("task.target_location", path=target_file))
    cmd = [sys.executable, engine_script, t("task.authoring_prompt") + str(target_file)]
    return subprocess.run(cmd, env=child_env).returncode


@click.command()
@click.option("--fix", is_flag=True, help="Auto-repair issues")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what --fix would change, without making any changes",
)
@click.pass_context
def doctor(ctx, fix, dry_run):  # type: ignore[no-untyped-def]
    _helpers._ensure_project_on_path(ctx.obj["root"])
    from core.doctor import run_doctor

    return run_doctor(fix=fix, dry_run=dry_run)


@click.command()
@click.option(
    "--show-token",
    is_flag=True,
    help="Print the Web UI token and exit, for opening the UI manually.",
)
@click.option(
    "--dev",
    is_flag=True,
    help=(
        "Serve the frontend from a live-reloading Vite dev server instead of "
        "the built bundle, so frontend edits need no rebuild."
    ),
)
@click.pass_context
def ui(ctx, show_token, dev):  # type: ignore[no-untyped-def]
    if show_token:
        from core.web.security import get_ui_token

        print(t("ui.token_line", token=get_ui_token()))
        return 0
    from .. import ui as _ui_mod

    return _ui_mod.run_ui_command(dev=dev)
