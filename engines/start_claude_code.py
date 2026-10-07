#!/usr/bin/env python3
"""自动启动 Claude Code 并执行任务 (统一架构版)"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# 确保能找到 core 模块
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.cli_utils import require_engine_cli
from core.engine_base import BaseEngine, register_signal_handler
from core.engine_base.launch_args import announce_launch, split_passthrough
from core.engine_base.plugin_dir_mixin import _PluginDirMixin, build_hooks_config
from core.task_lib import (
    TASK_FILE_SUFFIX,
    handle_task_mode,
    show_tasks,
)


class ClaudeEngine(_PluginDirMixin, BaseEngine):
    """Claude 引擎的具体实现。

    技能和钩子包成临时插件经 ``--plugin-dir`` 挂载，不写工作区的 ``.claude/``，
    见 :mod:`core.engine_base.plugin_dir_mixin`。
    """

    CLAUDE_COMMAND = "claude"
    CLAUDE_SKIP_PERMISSIONS_FLAG = "--dangerously-skip-permissions"
    EVENT_MAP = {
        "before_tool": "PreToolUse",
        "after_tool": "PostToolUse",
    }
    PLUGIN_MANIFEST_DIR = ".claude-plugin"

    def __init__(self):
        # Claude CLI has no --model flag in build_command(); the actual model
        # is whatever the local `claude` CLI is configured to use, so there's
        # no accurate value to store here.
        super().__init__("Claude", "")

    def _get_plugin_dir_root(self) -> Path:
        return Path.home() / ".codeagent" / "plugins" / "claude"

    def plugin_hooks_config(self) -> dict[str, Any] | None:
        return build_hooks_config(self.get_hooks_to_inject(), self.EVENT_MAP)

    def drop_legacy_workspace_injection(self, project: Path) -> None:
        """早先版本把钩子写进 ``.claude/settings.json``、把技能链进 ``.claude/skills``。"""
        scope = project / ".claude"

        def cleanup() -> None:
            self.settings_manager.restore_settings(scope / "settings.json")
            self.link_manager.cleanup_link_dir(scope / "skills")

        self.drop_legacy_injection(scope, cleanup)

    def build_command(
        self,
        message: str,
        non_interactive: bool,
        passthrough: Sequence[str] = (),
        plugin_dir: Path | None = None,
    ) -> list[str]:
        cmd = [self.CLAUDE_COMMAND, self.CLAUDE_SKIP_PERMISSIONS_FLAG]
        plugin_dirs = ([plugin_dir] if plugin_dir is not None else []) + (
            self.resolve_group_plugin_dirs()
        )
        for path in plugin_dirs:
            cmd.extend(["--plugin-dir", str(path)])
        cmd.extend(self.mcp_config_arg())
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

        Verified live: the
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

    project = Path.cwd()
    plugin_dir: Path | None = None

    def setup() -> None:
        nonlocal plugin_dir
        engine.drop_legacy_workspace_injection(project)
        plugin_dir = engine.ensure_plugin_dir(project)

    def teardown() -> None:
        engine.cleanup_plugin_dir(project)

    # 规范不由启动器投递：claude 自己读项目根的 AGENTS.md（已实测）。
    try:
        env = engine.env_manager.get_env()
        register_signal_handler()

        with engine.shared_injection(
            engine.plugin_session_scope(project), setup, teardown
        ):
            final_command = engine.build_command(
                engine.first_message(message),
                args.non_interactive,
                passthrough=passthrough,
                plugin_dir=plugin_dir,
            )
            announce_launch(engine.name)
            engine.run_shell(final_command, env)
    finally:
        engine.cleanup_temp_prompt()


if __name__ == "__main__":
    main()
