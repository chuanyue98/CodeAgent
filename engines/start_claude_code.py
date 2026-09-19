#!/usr/bin/env python3
"""自动启动 Claude Code 并执行任务 (统一架构版)"""
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
from core.engine_base.launch_args import split_passthrough
from core.engine_base.standards_report import report_standards_delivery
from core.services.sync_service import is_synced
from core.task_lib import (
    TASK_FILE_SUFFIX,
    handle_task_mode,
    show_tasks,
)


class ClaudeEngine(BaseEngine):
    """Claude 引擎的具体实现"""

    CLAUDE_COMMAND = "claude"
    CLAUDE_SKIP_PERMISSIONS_FLAG = "--dangerously-skip-permissions"
    EVENT_MAP = {
        "before_tool": "PreToolUse",
        "after_tool": "PostToolUse",
    }

    def __init__(self):
        # Claude CLI has no --model flag in build_command(); the actual model
        # is whatever the local `claude` CLI is configured to use, so there's
        # no accurate value to store here.
        super().__init__("Claude", "")

    def build_command(
        self,
        message: str,
        non_interactive: bool,
        standards_file: Path | None = None,
        passthrough: Sequence[str] = (),
    ) -> list[str]:
        cmd = [self.CLAUDE_COMMAND, self.CLAUDE_SKIP_PERMISSIONS_FLAG]
        for plugin_meta in self.get_plugins_to_mount():
            plugin_dir = plugin_meta.get("_plugin_dir")
            if plugin_dir:
                cmd.extend(["--plugin-dir", plugin_dir])
        if standards_file is not None:
            cmd.extend(["--append-system-prompt-file", str(standards_file)])
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

        Verified live (see docs/chatpage-cli-spike-results.md spike): the
        session id returned in the stream-json ``result``/``system`` events can
        be passed back via ``-r`` to resume with full prior context.
        """
        cmd = [
            self.CLAUDE_COMMAND,
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
    engine = ClaudeEngine()
    # 不接管 -h：ca claude --help 应该看到 claude 自己的帮助。
    parser = argparse.ArgumentParser(
        description="Claude Agent Controller", add_help=False, allow_abbrev=False
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
        help="YOLO 模式 (Claude 使用 --dangerously-skip-permissions)",
    )
    args, unknown = parser.parse_known_args()

    if args.list:
        show_tasks(label="Task List", file_suffix=TASK_FILE_SUFFIX)
        return

    if not require_engine_cli("claude"):
        sys.exit(1)

    message, passthrough = split_passthrough(unknown)
    if args.task is not None:
        task_prompt = handle_task_mode(
            args.task, label="Task", file_suffix=TASK_FILE_SUFFIX
        )
        if task_prompt:
            message = f"{message}\n\n{task_prompt}".strip()

    # 用户级已经 `ca sync` 过同一组时，规范和技能由 claude 自己加载，不再重复注入。
    synced = is_synced("claude", engine.get_current_project_group())

    def setup() -> None:
        if not synced:
            engine.ensure_skills_link(".claude/skills")
        engine.inject_hooks_to_settings(
            ".claude/settings.json", engine.get_hooks_to_inject()
        )

    def teardown() -> None:
        engine.restore_settings(".claude/settings.json")
        engine.cleanup_skills_link(".claude/skills")

    try:
        standards = "" if synced else engine.assemble_standards()
        report_standards_delivery("claude", engine.name, synced=synced)
        standards_file = (
            engine.write_temp_file(standards, suffix=".md") if standards else None
        )
        final_command = engine.build_command(
            engine.first_message(message),
            args.non_interactive,
            standards_file=standards_file,
            passthrough=passthrough,
        )
        env = engine.env_manager.get_env()
        register_signal_handler()

        with engine.shared_injection(Path.cwd() / ".claude", setup, teardown):
            print(f"🚀 Launching {engine.name}...")
            engine.run_shell(final_command, env)
    finally:
        engine.cleanup_temp_prompt()


if __name__ == "__main__":
    main()
