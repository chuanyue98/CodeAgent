#!/usr/bin/env python3
"""自动启动 CodeBuddy Code 并执行任务 (统一架构版)"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

# 确保能找到 core 模块
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.cli_utils import require_engine_cli
from core.engine_base import BaseEngine, register_signal_handler
from core.engine_base.launch_args import is_batch_shim, split_passthrough
from core.engine_base.standards_report import report_standards_delivery
from core.i18n import t
from core.services.sync_service import is_synced
from core.task_lib import (
    TASK_FILE_SUFFIX,
    handle_task_mode,
    show_tasks,
)


class CodeBuddyEngine(BaseEngine):
    """CodeBuddy 引擎的具体实现。

    与 Claude 引擎的主要差异：CodeBuddy 没有项目级 ``.codebuddy/settings.json``
    概念，因此不注入 Claude 风格的 skills/hooks（CodeBuddy 自带插件体系）。
    """

    COMMAND = "codebuddy"

    def __init__(self):
        super().__init__("CodeBuddy", "")

    def build_command(
        self,
        message: str,
        non_interactive: bool,
        standards: str = "",
        passthrough: Sequence[str] = (),
    ) -> list[str]:
        # ``auto`` 权限模式下，安全的工具调用自动通过，风险操作被拒绝，
        # 避免交互式授权卡住 ``ca`` 终端启动。
        cmd = [self.COMMAND, "--permission-mode", "auto"]
        # CodeBuddy 只有内联的 --append-system-prompt，没有 -file 版本。
        if standards:
            cmd.extend(["--append-system-prompt", standards])
        if non_interactive:
            cmd.append("-p")
        cmd.extend(passthrough)
        if message:
            cmd.append(message)
        return cmd

    def build_chat_command(
        self, message: str, session_id: str | None = None
    ) -> list[str]:
        """Builds a headless, structured-output command for one ChatPage turn.

        Uses CodeBuddy's print mode (``-p`` + ``stream-json``) and resumes with
        ``-r <session_id>`` when a prior session exists.
        """
        cmd = [
            self.COMMAND,
            "-p",
            "--output-format",
            "stream-json",
            "--include-partial-messages",
            "--verbose",
            "--permission-mode",
            "dontAsk",
        ]
        if session_id:
            cmd.extend(["-r", session_id])
        cmd.append(message)
        return cmd


def main():
    engine = CodeBuddyEngine()
    parser = argparse.ArgumentParser(
        description="CodeBuddy Agent Controller", add_help=False, allow_abbrev=False
    )
    parser.add_argument("-t", "--task", nargs="?", const="", help="任务模式")
    parser.add_argument("--list", action="store_true", help="列出所有任务")
    parser.add_argument(
        "-ni", "--non-interactive", action="store_true", help="非交互模式"
    )
    parser.add_argument(
        "-y",
        "--yolo",
        action="store_true",
        help="YOLO 模式 (CodeBuddy 使用 --permission-mode auto)",
    )
    args, unknown = parser.parse_known_args()

    if args.list:
        show_tasks(label="Task List", file_suffix=TASK_FILE_SUFFIX)
        return

    if not require_engine_cli("codebuddy"):
        sys.exit(1)

    message, passthrough = split_passthrough(unknown)
    if args.task is not None:
        task_prompt = handle_task_mode(
            args.task, label="Task", file_suffix=TASK_FILE_SUFFIX
        )
        if task_prompt:
            message = f"{message}\n\n{task_prompt}".strip()

    env = engine.env_manager.get_env()
    # 用户级已经 `ca sync` 过同一组时，规范由 codebuddy 自己加载，不再重复注入。
    synced = is_synced("codebuddy", engine.get_current_project_group())
    standards = "" if synced else engine.assemble_standards()
    skip_reason = ""
    if standards and is_batch_shim(engine.COMMAND, env):
        skip_reason = t("engine.standards_skip_batch_shim_reason")
        standards = ""
    report_standards_delivery(
        "codebuddy", engine.name, synced=synced, skip_reason=skip_reason
    )

    try:
        final_command = engine.build_command(
            engine.first_message(message),
            args.non_interactive,
            standards=standards,
            passthrough=passthrough,
        )
        register_signal_handler()
        print(f"🚀 Launching {engine.name}...")
        engine.run_shell(final_command, env)
    finally:
        engine.cleanup_temp_prompt()


if __name__ == "__main__":
    main()
