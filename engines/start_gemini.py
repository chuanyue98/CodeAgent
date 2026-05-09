#!/usr/bin/env python3
"""自动启动 Gemini 并执行任务 (统一架构版)"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List

# 确保能找到 core 模块
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.engine_base import BaseEngine
from core.task_lib import (
    TASK_FILE_SUFFIX,
    handle_task_mode,
    set_additional_template_search_paths,
    show_tasks,
)

# 设置提示词模板搜索路径
set_additional_template_search_paths([Path(__file__).resolve().parent.parent])


class GeminiEngine(BaseEngine):
    """Gemini 引擎的具体实现"""

    EVENT_MAP = {
        "before_tool": "BeforeTool",
        "after_tool": "AfterTool",
    }

    def _get_global_ext_dir(self):
        return (Path.home() / ".gemini" / "extensions").absolute()

    def __init__(self):
        super().__init__("Gemini", "gemini-3-flash-preview")

    def build_command(
        self,
        message: str,
        model_name: str,
        non_interactive: bool,
        approval_mode: str = "auto_edit",
    ) -> List[str]:
        # 基础命令列表
        cmd = ["gemini", "--model", model_name, "--approval-mode", approval_mode]

        if not non_interactive:
            cmd.append("-i")

        cmd.append(message)
        return cmd

    def run_engine(self, cmd: List[str], env: dict):
        """执行引擎命令"""
        self.run_shell(cmd, env)

    def select_model_interactive(self, non_interactive: bool, timeout=3) -> str:
        """返回默认模型"""
        return self.default_model

    def _format_plugins_for_settings(self, data: dict, plugins: List[dict]) -> dict:
        """实现 Gemini 特有的扩展注册逻辑 (严格 Session 控制)"""
        # 获取当前 CodeAgent 允许的插件名集合
        allowed_plugin_names = {p["name"] for p in plugins}

        # 如果 settings.json 里已有 extensions，先全部禁用
        if "extensions" in data and isinstance(data["extensions"], dict):
            for ext_name in data["extensions"]:
                if ext_name not in allowed_plugin_names:
                    data["extensions"][ext_name]["enabled"] = False
        else:
            data["extensions"] = {}

        # 仅开启 CodeAgent 允许的插件
        for plugin_meta in plugins:
            plugin_name = plugin_meta["name"]
            plugin_path = plugin_meta.get("_plugin_dir")

            if not plugin_path:
                continue

            data["extensions"][plugin_name] = {
                "type": "local",
                "path": str(Path(plugin_path).absolute().as_posix()),
                "enabled": True,
            }
        return data


def main():
    engine = GeminiEngine()
    parser = argparse.ArgumentParser(description="Gemini Agent Controller")
    parser.add_argument("-t", "--task", nargs="?", const="", help="任务模式")
    parser.add_argument("-pr", "--pr-url", help="代码审查 PR URL")
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
    args, extra_args = parser.parse_known_args()

    if args.list:
        show_tasks(label="Task List", file_suffix=TASK_FILE_SUFFIX)
        sys.exit(0)

    # 默认即为 yolo 模式
    approval_mode = "yolo"

    selected_model = engine.select_model_interactive(args.non_interactive)
    env = engine.env_manager.get_env()

    if args.pr_url:
        os.environ["PR_URL"] = args.pr_url

    # 使用基类统一合成提示词 (支持 review 模式)
    full_prompt = engine.assemble_prompt(
        task=" ".join(extra_args), is_review=bool(args.pr_url)
    )

    if args.task is not None:
        task_prompt = handle_task_mode(args.task, file_suffix=TASK_FILE_SUFFIX)
        if task_prompt:
            full_prompt = f"{full_prompt}\n\n{task_prompt}"

    # 临时文件处理
    concise_msg = engine.write_temp_prompt(full_prompt)

    # 统一技能链接
    engine.ensure_skills_link(".gemini/skills")
    # 挂载插件 (创建全局临时映射以满足 Gemini CLI 加载要求)
    engine.ensure_plugins_link()

    # 注入动态钩子
    resolved_hooks = engine.get_hooks_to_inject()
    engine.inject_hooks_to_settings(".gemini/settings.json", resolved_hooks)
    # 注册已挂载插件
    engine.inject_plugins_to_settings(".gemini/settings.json")

    try:
        final_cmd = engine.build_command(
            concise_msg,
            selected_model,
            args.non_interactive,
            approval_mode=approval_mode,
        )
        print(
            f"🚀 Launching {engine.name} ({selected_model}) in {approval_mode} mode..."
        )
        engine.run_engine(final_cmd, env)
    finally:
        # 1. 还原配置到注入前状态
        engine.restore_settings(".gemini/settings.json")
        # 2. 清理技能链接，保持项目纯净
        engine.cleanup_skills_link(".gemini/skills")
        # 3. 使用基类统一清理临时提示词
        engine.cleanup_temp_prompt()


if __name__ == "__main__":
    main()
