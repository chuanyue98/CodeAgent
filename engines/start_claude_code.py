#!/usr/bin/env python3
"""自动启动 Claude Code 并执行任务 (统一架构版)"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

# 确保能找到 core 模块
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.engine_base import BaseEngine
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

    def _get_plugin_link_dir(self):
        return (Path.cwd() / ".claude" / "plugins").absolute()

    def __init__(self):
        super().__init__("Claude", "claude-3-5-sonnet")

    def build_command(self, message: str, non_interactive: bool) -> List[str]:
        # 构建命令列表以绕过 Windows 长度限制
        cmd = [self.CLAUDE_COMMAND, self.CLAUDE_SKIP_PERMISSIONS_FLAG]

        # 目前 Claude CLI 对非交互模式的支持各异，暂不加额外 flag
        # 直接追加消息内容
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
    args, unknown = parser.parse_known_args()

    if args.list:
        show_tasks(label="Task List", file_suffix=TASK_FILE_SUFFIX)
        return

    # 使用基类统一合成提示词
    full_prompt = engine.assemble_prompt(task=" ".join(unknown))

    if args.task is not None:
        task_prompt = handle_task_mode(
            args.task, label="Task", file_suffix=TASK_FILE_SUFFIX
        )
        if task_prompt:
            full_prompt = f"{full_prompt}\n\n{task_prompt}"

    # 使用临时文件引导模式 (关键：解决命令行超长问题)
    concise_msg = engine.write_temp_prompt(full_prompt)

    # 统一技能链接
    engine.ensure_skills_link(".claude/skills")
    # 统一插件链接
    engine.ensure_plugins_link()

    # 注入动态钩子
    resolved_hooks = engine.get_hooks_to_inject()
    engine.inject_hooks_to_settings(".claude/settings.json", resolved_hooks)

    env = engine.env_manager.get_env()

    try:
        final_command = engine.build_command(concise_msg, args.non_interactive)
        print(f"🚀 Launching {engine.name} ({engine.default_model})...")

        # 强制检查：确保 message 真的只是 concise_msg
        if len(str(final_command)) > 1000:
            print("⚠️ Warning: Command list still seems too long. Checking structure...")

        engine.run_shell(final_command, env)
    finally:
        # 1. 还原配置到注入前状态
        engine.restore_settings(".claude/settings.json")
        # 2. 清理技能链接，保持项目纯净
        engine.cleanup_skills_link(".claude/skills")
        # 3. 清理插件链接
        engine.cleanup_plugins_link()
        # 4. 使用基类统一清理临时提示词
        engine.cleanup_temp_prompt()


if __name__ == "__main__":
    main()
