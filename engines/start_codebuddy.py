#!/usr/bin/env python3
"""自动启动 CodeBuddy Code 并执行任务 (统一架构版)"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 确保能找到 core 模块
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.cli_utils import require_engine_cli
from core.engine_base import BaseEngine, register_signal_handler
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

    def build_command(self, message: str, non_interactive: bool) -> list[str]:
        # ``auto`` 权限模式下，安全的工具调用自动通过，风险操作被拒绝，
        # 避免交互式授权卡住 ``ca`` 终端启动。
        cmd = [self.COMMAND, "--permission-mode", "auto"]
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
    parser = argparse.ArgumentParser(description="CodeBuddy Agent Controller")
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

    # 使用基类统一合成提示词
    full_prompt = engine.assemble_prompt(task=" ".join(unknown))

    if args.task is not None:
        task_prompt = handle_task_mode(
            args.task, label="Task", file_suffix=TASK_FILE_SUFFIX
        )
        if task_prompt:
            full_prompt = f"{full_prompt}\n\n{task_prompt}"

    resource_lock = engine.acquire_resource_lock(
        Path.cwd() / ".codebuddy" / ".codeagent-session.lock"
    )
    try:
        # 使用临时文件引导模式 (关键：解决命令行超长问题)
        concise_msg = engine.write_temp_prompt(full_prompt)

        env = engine.env_manager.get_env()
        register_signal_handler()

        final_command = engine.build_command(concise_msg, args.non_interactive)
        print(f"🚀 Launching {engine.name}...")

        engine.run_shell(final_command, env)
    finally:
        # 使用基类统一清理临时提示词
        engine.cleanup_temp_prompt()
        engine.release_resource_lock(resource_lock)


if __name__ == "__main__":
    main()
