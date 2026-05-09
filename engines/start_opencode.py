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

    def _get_plugin_link_dir(self):
        return (Path.cwd() / ".opencode" / "plugins").absolute()

    def ensure_plugins_link(self):
        """为 OpenCode 优化插件挂载逻辑：支持扁平化链接以符合 OpenCode 的扫描规范"""
        plugins_to_mount = self.get_plugins_to_mount()
        if not plugins_to_mount:
            return

        link_dir = self._get_plugin_link_dir()
        link_dir.mkdir(parents=True, exist_ok=True)

        mounted_count = 0
        for plugin_meta in plugins_to_mount:
            plugin_name = plugin_meta["name"]
            plugin_src_str = plugin_meta.get("_plugin_dir")
            if not plugin_src_str:
                continue

            plugin_src = Path(plugin_src_str).resolve()

            # 策略：如果插件内部有 .opencode/plugins 目录，则直接挂载其内部内容（扁平化）
            # 否则挂载整个插件目录
            opencode_inner_plugins = plugin_src / ".opencode" / "plugins"
            if opencode_inner_plugins.is_dir():
                # 挂载内部所有的 .js/.ts 文件
                for item in opencode_inner_plugins.iterdir():
                    if item.is_file() and item.suffix in (".js", ".ts"):
                        target_link = link_dir / item.name
                        self._safe_remove_link(target_link)
                        self._create_skill_link(item, target_link)
                        mounted_count += 1
            else:
                # 降级方案：挂载整个文件夹
                target_link = link_dir / plugin_name
                self._safe_remove_link(target_link)
                self._create_skill_link(plugin_src, target_link)
                mounted_count += 1

        if mounted_count:
            print(f"🔌 Ensured {mounted_count} flattened plugin links in {link_dir}")

    def cleanup_plugins_link(self):
        """清理所有创建的链接，不限于文件夹"""
        link_dir = self._get_plugin_link_dir()
        if not link_dir.exists():
            return

        for item in link_dir.iterdir():
            if self._is_windows_link(item) or item.is_symlink():
                self._safe_remove_link(item)

        # 如果目录空了则删除
        if not any(link_dir.iterdir()):
            try:
                link_dir.rmdir()
            except Exception:
                pass

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
    engine.ensure_plugins_link()

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
        engine.cleanup_plugins_link()
        # 4. 使用基类统一清理临时提示词
        engine.cleanup_temp_prompt()


if __name__ == "__main__":
    main()
