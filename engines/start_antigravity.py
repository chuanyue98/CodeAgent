#!/usr/bin/env python3
"""自动启动 Google Antigravity (agy) 并执行任务 (统一架构版)"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.cli_utils import require_engine_cli
from core.engine_base import BaseEngine, register_signal_handler
from core.engine_base.launch_args import split_passthrough
from core.engine_base.standards_report import report_standards_delivery
from core.services.sync_service import is_synced
from core.task_lib import (
    TASK_FILE_SUFFIX,
    handle_task_mode,
    show_tasks,
)


class AntigravityEngine(BaseEngine):
    """Google Antigravity (agy) 引擎实现。"""

    COMMAND = "agy"

    def __init__(self) -> None:
        super().__init__("Antigravity", "")

    def build_command(
        self,
        message: str,
        non_interactive: bool = False,
        yolo: bool = False,
        passthrough: Sequence[str] = (),
    ) -> list[str]:
        cmd = [self.COMMAND, *passthrough]
        if non_interactive:
            cmd.extend(["-p", message, "--output-format", "json"])
        else:
            if message:
                cmd.extend(["-i", message])
        if yolo:
            cmd.append("--dangerously-skip-permissions")
        return cmd

    def build_chat_command(
        self, message: str, session_id: str | None = None
    ) -> list[str]:
        cmd = [
            self.COMMAND,
            "-p",
            message,
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
        ]
        if session_id:
            cmd.extend(["--conversation", session_id])
        return cmd


def main() -> None:
    engine = AntigravityEngine()
    parser = argparse.ArgumentParser(
        description="Antigravity Agent Controller", add_help=False, allow_abbrev=False
    )
    parser.add_argument("-t", "--task", nargs="?", const="", help="任务模式")
    parser.add_argument("--list", action="store_true", help="列出所有任务")
    parser.add_argument(
        "-ni", "--non-interactive", action="store_true", help="非交互模式"
    )
    parser.add_argument(
        "-y", "--yolo", action="store_true", default=True, help="YOLO 模式"
    )
    args, unknown = parser.parse_known_args()

    if args.list:
        show_tasks(label="Task List", file_suffix=TASK_FILE_SUFFIX)
        return

    if not require_engine_cli("agy"):
        sys.exit(1)

    message, passthrough = split_passthrough(unknown)
    if args.task is not None:
        task_prompt = handle_task_mode(args.task, file_suffix=TASK_FILE_SUFFIX)
        if isinstance(task_prompt, str) and task_prompt:
            message = f"{message}\n\n{task_prompt}".strip() if message else task_prompt

    env = engine.env_manager.get_env()
    register_signal_handler()

    # Antigravity 没有 system-prompt 通道，规范只能靠 `ca sync` 写进用户级
    # GEMINI.md。这里把结论明确报出来，不再静默丢掉。
    synced = is_synced("antigravity", engine.get_current_project_group())
    report_standards_delivery("antigravity", engine.name, synced=synced)

    final_command = engine.build_command(
        message, args.non_interactive, yolo=args.yolo, passthrough=passthrough
    )
    print(f"🚀 Launching {engine.name}...")
    engine.run_shell(final_command, env)


if __name__ == "__main__":
    main()
