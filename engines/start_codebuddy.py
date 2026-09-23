#!/usr/bin/env python3
"""自动启动 CodeBuddy Code 并执行任务 (统一架构版)"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

# 确保能找到 core 模块
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.cli_utils import require_engine_cli
from core.engine_base import BaseEngine, register_signal_handler
from core.engine_base.launch_args import announce_launch, split_passthrough
from core.engine_base.plugin_dir_mixin import _PluginDirMixin
from core.task_lib import (
    TASK_FILE_SUFFIX,
    handle_task_mode,
    show_tasks,
)
from core.utils.atomic_write import atomic_write

#: 早先版本注册的本地市场名，现在只用来清理。
_LEGACY_MARKETPLACE = "codeagent-local"


class CodeBuddyEngine(_PluginDirMixin, BaseEngine):
    """CodeBuddy 引擎的具体实现。

    与 Claude 引擎的主要差异：CodeBuddy 没有项目级 ``.codebuddy/settings.json``
    概念，也不认 Claude 风格的 ``skills/`` 目录——技能要包成插件挂载，
    见 :mod:`core.engine_base.plugin_dir_mixin`。
    """

    COMMAND = "codebuddy"

    def __init__(self):
        super().__init__("CodeBuddy", "")

    def _get_codebuddy_home(self) -> Path:
        configured = os.environ.get("CODEBUDDY_CONFIG_DIR", "").strip()
        return Path(configured) if configured else Path.home() / ".codebuddy"

    def _get_plugin_dir_root(self) -> Path:
        return self._get_codebuddy_home() / ".tmp" / "plugins"

    def drop_legacy_marketplace(self) -> None:
        """摘掉早先版本注册的本地市场。

        那版靠市场分发技能，注册写在用户级配置里、只在正常退出时撤销，会话被
        强杀就会永久留下一条指向我们已不再维护的目录的记录。
        """
        home = self._get_codebuddy_home()
        known_path = home / "plugins" / "known_marketplaces.json"
        try:
            known = json.loads(known_path.read_text(encoding="utf-8"))
        except Exception:
            known = None
        if isinstance(known, dict) and known.pop(_LEGACY_MARKETPLACE, None) is not None:
            if known:
                atomic_write(
                    known_path, json.dumps(known, indent=2, ensure_ascii=False)
                )
            else:
                known_path.unlink(missing_ok=True)
        shutil.rmtree(
            home / ".tmp" / "marketplaces" / _LEGACY_MARKETPLACE, ignore_errors=True
        )

    def build_command(
        self,
        message: str,
        non_interactive: bool,
        passthrough: Sequence[str] = (),
    ) -> list[str]:
        # ``auto`` 权限模式下，安全的工具调用自动通过，风险操作被拒绝，
        # 避免交互式授权卡住 ``ca`` 终端启动。
        cmd = [
            self.COMMAND,
            "--permission-mode",
            "auto",
            *self.mcp_config_arg(),
            *self.delegation_agent_arg(),
        ]
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
    # 规范不由启动器投递：codebuddy 自己读项目根的 AGENTS.md。

    project = Path.cwd()
    plugin_dir: Path | None = None

    def setup() -> None:
        nonlocal plugin_dir
        engine.drop_legacy_marketplace()
        plugin_dir = engine.ensure_plugin_dir(project)

    def teardown() -> None:
        engine.cleanup_plugin_dir(project)

    try:
        with engine.shared_injection(project, setup, teardown):
            final_command = engine.build_command(
                engine.first_message(message),
                args.non_interactive,
                passthrough=passthrough,
            )
            register_signal_handler()
            announce_launch(engine.name)
            engine.run_shell(
                final_command, {**env, **engine.plugin_dir_env(plugin_dir)}
            )
    finally:
        engine.cleanup_temp_prompt()


if __name__ == "__main__":
    main()
