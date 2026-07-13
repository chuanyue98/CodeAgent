#!/usr/bin/env python3
"""自动启动 Claude Code 并执行任务 (统一架构版)"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

# 确保能找到 core 模块
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.cli_utils import require_engine_cli
from core.engine_base import BaseEngine, register_signal_handler

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
        super().__init__("Claude", "claude-3-5-sonnet")

    def build_command(self, message: str, non_interactive: bool) -> List[str]:
        cmd = [self.CLAUDE_COMMAND, self.CLAUDE_SKIP_PERMISSIONS_FLAG]
        for plugin_meta in self.get_plugins_to_mount():
            plugin_dir = plugin_meta.get("_plugin_dir")
            if plugin_dir:
                cmd.extend(["--plugin-dir", plugin_dir])
        cmd.append(message)
        return cmd

    def build_chat_command(
        self, message: str, session_id: Optional[str] = None
    ) -> List[str]:
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
            self.CLAUDE_SKIP_PERMISSIONS_FLAG,
        ]
        if session_id:
            cmd.extend(["-r", session_id])
        cmd.append(message)
        return cmd


def main():
    engine = ClaudeEngine()
    parser = argparse.ArgumentParser(description="Claude Agent Controller")
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

    # 使用基类统一合成提示词
    full_prompt = engine.assemble_prompt(task=" ".join(unknown))

    if args.task is not None:
        task_prompt = handle_task_mode(
            args.task, label="Task", file_suffix=TASK_FILE_SUFFIX
        )
        if task_prompt:
            full_prompt = f"{full_prompt}\n\n{task_prompt}"

    resource_lock = engine.acquire_resource_lock(
        Path.cwd() / ".claude" / ".codeagent-session.lock"
    )
    try:
        # 使用临时文件引导模式 (关键：解决命令行超长问题)
        concise_msg = engine.write_temp_prompt(full_prompt)

        # 统一技能链接
        engine.ensure_skills_link(".claude/skills")

        # 注入动态钩子
        resolved_hooks = engine.get_hooks_to_inject()
        engine.inject_hooks_to_settings(".claude/settings.json", resolved_hooks)

        env = engine.env_manager.get_env()
        register_signal_handler()

        final_command = engine.build_command(concise_msg, args.non_interactive)
        print(f"🚀 Launching {engine.name} ({engine.default_model})...")

        engine.run_shell(final_command, env)
    finally:
        try:
            # 1. 还原配置到注入前状态
            engine.restore_settings(".claude/settings.json")
            # 2. 清理技能链接，保持项目纯净
            engine.cleanup_skills_link(".claude/skills")
            # 3. 使用基类统一清理临时提示词
            engine.cleanup_temp_prompt()
        finally:
            engine.release_resource_lock(resource_lock)


if __name__ == "__main__":
    main()
