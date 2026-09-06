#!/usr/bin/env python3
"""自动启动 Freebuff (免费版 CLI) 并执行任务 (统一架构版)

接入状态（对标 codebuddy，headless 缺失项预留）：
  - ✅ 交互式 TUI 启动（``ca freebuff``、浏览器终端卡片走 ca_launcher 也会
    到这里）；Freebuff 原生读取 AGENTS.md/CLAUDE.md 这类知识文件，skills/
    等资源就在仓库里，无需也**无法**做 Claude 风格的 settings 注入。
  - ✅ ``--continue <会话id>`` 恢复由 core/services/resume_commands.py 提供
    （Web 历史页/``ca history`` 恢复路径），不经过本脚本。
  - ❌ 预留：任务模式（-t/--task）、非交互（--non-interactive/-ni）与 headless
    单轮都依赖 print/ACP 通道，而 freebuff 免费版 CLI（实测 0.0.168）没有
    --print/--json/--acp 这类选项（上游 open issue #947 正是要这个）。这些
    入口到此为止：报清晰错误并以非零码退出，后台任务/调度立刻可见失败原因，
    而不是把交互 TUI 拉进没有 TTY 的后台挂起。
"""
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
    show_tasks,
)


class FreebuffEngine(BaseEngine):
    """Freebuff (免费版 CLI) 引擎实现。

    与其它引擎的差异：Freebuff 是登录制云产品，系统提示词由产品侧下发，
    CodeAgent 无法（也不需要）像 claude/codex 那样注入 skills/hooks——
    本仓库根目录的 AGENTS.md 会被它原生读取。因此本引擎不写任何 settings
    注入文件，交互启动就是裸拉起 TUI。
    """

    COMMAND = "freebuff"

    def __init__(self):
        super().__init__("Freebuff", "")

    def build_command(self, message: str, non_interactive: bool) -> list[str]:
        # 交互 TUI：不带 message（免费版 CLI 没有接受初始消息的通道，实测
        # 传未知参数会报 unknown option，只会让启动失败）。
        if non_interactive:
            raise NotImplementedError(
                "Freebuff 免费版 CLI 没有 headless 通道，无法非交互运行"
            )
        return [self.COMMAND]

    def build_chat_command(
        self, message: str, session_id: str | None = None
    ) -> list[str]:
        """Headless 单轮命令——预留占位，见模块 docstring。"""
        raise NotImplementedError(
            "Freebuff 免费版 CLI 没有 headless/print 通道，Chat 单轮暂不可用"
        )


def main():
    engine = FreebuffEngine()
    parser = argparse.ArgumentParser(description="Freebuff Agent Controller")
    parser.add_argument("-t", "--task", nargs="?", const="", help="任务模式")
    parser.add_argument("--list", action="store_true", help="列出所有任务")
    parser.add_argument(
        "-ni", "--non-interactive", action="store_true", help="非交互模式"
    )
    parser.add_argument(
        "-y",
        "--yolo",
        action="store_true",
        help="YOLO 模式 (freebuff 无对应 flag，忽略)",
    )
    args, unknown = parser.parse_known_args()

    if args.list:
        show_tasks(label="Task List", file_suffix=TASK_FILE_SUFFIX)
        return

    if not require_engine_cli("freebuff"):
        sys.exit(1)

    # 预留的 headless 入口：任务模式/非交互都需要非交互地跑完整轮次，而
    # freebuff 免费 CLI 没有该通道。在这里明确失败（exit 1），让后台任务/
    # 调度/batch-run 在日志里留下可读的原因，而不是把 TUI 挂进无 TTY 后台。
    if args.task is not None or args.non_interactive:
        print(
            "❌ Freebuff 免费版 CLI 没有 headless 通道：任务模式(-t)与"
            "非交互(-ni)暂不支持。\n"
            "   交互式启动用 `ca freebuff`；后台任务/调度/batch-run 请改用 "
            "claude / codex / opencode / codebuddy。",
            file=sys.stderr,
        )
        sys.exit(1)

    if unknown:
        print(
            "⚠️  Freebuff 交互模式不接受初始消息参数，已忽略: "
            + " ".join(unknown),
            file=sys.stderr,
        )

    env = engine.env_manager.get_env()
    register_signal_handler()

    final_command = engine.build_command("", args.non_interactive)
    print(f"🚀 Launching {engine.name}...")

    engine.run_shell(final_command, env)


if __name__ == "__main__":
    main()
