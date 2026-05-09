#!/usr/bin/env python3
"""自动启动 OpenCode 并执行任务 (统一架构版)"""
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


class OpenCodeEngine(BaseEngine):
    """OpenCode 引擎的具体实现"""

    OPENCODE_COMMAND = "opencode"

    def __init__(self):
        super().__init__("OpenCode", "opencode-default")

    def build_command(self, message: str, non_interactive: bool) -> List[str]:
        if non_interactive:
            # 非交互模式使用 run
            return [self.OPENCODE_COMMAND, "run", message]

        # 交互模式：在当前目录启动 TUI 并注入初始提示词
        return [self.OPENCODE_COMMAND, ".", "--prompt", message]


def main():
    engine = OpenCodeEngine()
    parser = argparse.ArgumentParser(description="OpenCode Agent Controller")
    parser.add_argument("-t", "--task", nargs="?", const="", help="任务模式")
    parser.add_argument("--list", action="store_true", help="列出所有任务")
    parser.add_argument(
        "-ni", "--non-interactive", action="store_true", help="非交互模式"
    )
    parser.add_argument(
        "-y",
        "--yolo",
        action="store_true",
        default=True,
        help="开启 YOLO 模式 (默认开启)",
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

    # 使用临时文件引导模式，解决命令行超长问题
    concise_msg = engine.write_temp_prompt(full_prompt)

    # 统一技能链接 (挂载到 .opencode/skills)
    engine.ensure_skills_link(".opencode/skills")
    # 统一插件链接
    engine.ensure_plugins_link(".opencode/plugins")

    # 注入动态钩子
    resolved_hooks = engine.get_hooks_to_inject()
    engine.inject_hooks_to_settings(".opencode/settings.json", resolved_hooks)

    env = engine.env_manager.get_env()

    try:
        final_command = engine.build_command(concise_msg, args.non_interactive)
        print(f"🚀 Launching {engine.name}...")

        engine.run_shell(final_command, env)
    finally:
        # 1. 还原配置到注入前状态
        engine.restore_settings(".opencode/settings.json")
        # 2. 清理技能链接
        engine.cleanup_skills_link(".opencode/skills")
        # 3. 清理插件链接
        engine.cleanup_plugins_link(".opencode/plugins")
        # 4. 使用基类统一清理临时提示词
        engine.cleanup_temp_prompt()


if __name__ == "__main__":
    main()
