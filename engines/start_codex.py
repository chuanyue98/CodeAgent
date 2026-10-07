#!/usr/bin/env python3
"""Launch Codex with dynamic prompt/skills injection and optional task/code-plan mode."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

# Ensure core modules are importable when running as a script.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.cli_utils import require_engine_cli
from core.engine_base import BaseEngine, register_signal_handler
from core.engine_base.launch_args import announce_launch, split_passthrough
from core.i18n import t
from core.logging_config import get_logger
from core.task_lib import (
    TASK_FILE_SUFFIX,
    handle_task_mode,
    set_additional_template_search_paths,
    show_tasks,
)
from engines.code_plans import (
    CODE_PLAN_DIR_PATTERN,
    CODE_PLAN_FILE_SUFFIX,
    CODE_PLAN_HISTORY_FILENAME,
    find_directories_for_plan,
    get_code_plan_history_path,
    list_code_plan_directories,
    load_code_plan_history,
    save_code_plan_history,
    select_code_plan_directory_interactively,
    split_code_plan_argument,
    update_code_plan_history,
)
from engines.codex_plugins import CodexPluginMixin
from engines.shell_first import (
    SHELL_FIRST_ALLOW_ENV,
    SHELL_FIRST_MARKER,
    _resolve_shell,
    _shell_first_allowed_via_override,
    extract_shell_first_blocks,
    run_prelaunch_commands,
)

__all__ = [
    "CodexEngine",
    "subprocess",
    "shutil",
    "SHELL_FIRST_ALLOW_ENV",
    "SHELL_FIRST_MARKER",
    "_resolve_shell",
    "_shell_first_allowed_via_override",
    "extract_shell_first_blocks",
    "run_prelaunch_commands",
    "CODE_PLAN_DIR_PATTERN",
    "CODE_PLAN_FILE_SUFFIX",
    "CODE_PLAN_HISTORY_FILENAME",
    "find_directories_for_plan",
    "get_code_plan_history_path",
    "list_code_plan_directories",
    "load_code_plan_history",
    "save_code_plan_history",
    "select_code_plan_directory_interactively",
    "split_code_plan_argument",
    "update_code_plan_history",
    "parse_arguments",
    "main",
]

CODEX_COMMAND = "codex"
CODEX_EXEC_SUBCOMMAND = "exec"
CODEX_SKIP_PERMISSIONS_FLAG = "--dangerously-bypass-approvals-and-sandbox"
# 会开出会话的子命令：注入的参数跟在子命令后面（这几个都接受 -c 与 bypass）。
CODEX_SESSION_SUBCOMMANDS = frozenset({"exec", "e", "resume", "fork"})
# 其余子命令与会话无关，原样透传、不注入。
CODEX_OTHER_SUBCOMMANDS = frozenset(
    {
        "review",
        "login",
        "logout",
        "mcp",
        "plugin",
        "mcp-server",
        "app-server",
        "remote-control",
        "completion",
        "update",
        "doctor",
        "sandbox",
        "debug",
        "apply",
        "a",
        "archive",
        "delete",
        "unarchive",
        "cloud",
        "exec-server",
        "features",
        "help",
    }
)


logger = get_logger(__name__)

set_additional_template_search_paths([Path(__file__).resolve().parent.parent])


class CodexEngine(CodexPluginMixin, BaseEngine):
    """Codex engine adapter using shared CodeAgent base behavior."""

    MARKETPLACE_NAME = "codeagent-local"
    READS_AGENTS_SKILLS = True

    # Confirmed live against codex-cli 0.142.5 via the app-server's
    # ``hooks/list`` method: codex uses the same PascalCase event names and the
    # same matcher-group structure as Claude, just expressed in TOML.
    EVENT_MAP = {
        "before_tool": "PreToolUse",
        "after_tool": "PostToolUse",
    }

    def __init__(self) -> None:
        super().__init__("Codex", "codex-default")

    def _format_plugins_for_settings(
        self, data: Any, plugins: list[dict[str, Any]]
    ) -> Any:
        return CodexPluginMixin._format_plugins_for_settings(self, data, plugins)

    def warn_if_project_untrusted(self) -> None:
        """Warns when codex will silently ignore the hooks just injected.

        Project-local ``.codex/config.toml`` — hooks included — is only loaded
        for projects marked trusted in the user-level ``~/.codex/config.toml``.
        Without that entry codex starts normally and drops the hooks without
        any error, so surface it here rather than let it fail silently.
        """
        project = Path.cwd().resolve()
        try:
            config = self._load_config(self._get_user_config_path())
            projects = (config or {}).get("projects", {}) or {}
            entry = None
            for key, value in projects.items():
                try:
                    if Path(key).resolve() == project:
                        entry = value
                        break
                except OSError:
                    continue
            trust = (entry or {}).get("trust_level") if entry else None
        except Exception:
            return

        if trust != "trusted":
            print(
                f"⚠️  Codex will ignore the injected hooks: '{project}' is not a "
                "trusted project.\n"
                f"   Add this to {self._get_user_config_path()} to enable them:\n"
                f'   [projects."{project}"]\n'
                '   trust_level = "trusted"'
            )

    def build_command(
        self,
        message: str = "",
        non_interactive: bool = False,
        yolo: bool = False,
        passthrough: Sequence[str] = (),
    ) -> list[str]:
        effective_yolo = (
            yolo
            or getattr(self, "yolo", False)
            or os.environ.get("CA_YOLO", "").lower() in ("1", "true")
        )
        rest = list(passthrough)
        if rest and rest[0] in CODEX_OTHER_SUBCOMMANDS:
            return [CODEX_COMMAND, *rest]

        cmd = [CODEX_COMMAND]
        if rest and rest[0] in CODEX_SESSION_SUBCOMMANDS:
            cmd.append(rest.pop(0))
            bypass = effective_yolo
        elif non_interactive:
            cmd.append(CODEX_EXEC_SUBCOMMAND)
            bypass = True
        else:
            bypass = effective_yolo
        if bypass:
            cmd.append(CODEX_SKIP_PERMISSIONS_FLAG)
        cmd.extend(self.codex_mcp_overrides())
        cmd.extend(rest)
        if message:
            cmd.append(message)
        return cmd

    def build_interactive_command(
        self, message: str = "", yolo: bool = False
    ) -> list[str]:
        return self.build_command(message, non_interactive=False, yolo=yolo)

    def build_chat_command(
        self, message: str, session_id: str | None = None
    ) -> list[str]:
        """Builds a headless JSON command for one ChatPage turn.

        Verified live:
        ``codex exec resume <thread_id>`` carries full prior context forward.
        """
        if session_id:
            return [
                CODEX_COMMAND,
                CODEX_EXEC_SUBCOMMAND,
                "resume",
                session_id,
                "--json",
                "--sandbox",
                "workspace-write",
                message,
            ]
        return [
            CODEX_COMMAND,
            CODEX_EXEC_SUBCOMMAND,
            "--json",
            "--sandbox",
            "workspace-write",
            message,
        ]

    def _get_plugin_link_dir(self) -> Path:
        return (Path.home() / ".codex" / "plugins").absolute()

    def _load_config(self, path: Path) -> Any:
        """重写：支持 TOML 格式加载"""
        import tomlkit

        if not path.exists():
            return tomlkit.parse("")
        try:
            content = path.read_text(encoding="utf-8")
            return tomlkit.parse(content)
        except Exception as exc:
            logger.warning("Failed to parse TOML config from %s: %s", path, exc)
            return None

    def _save_config(self, path: Path, data: Any):
        """重写：支持 TOML 格式保存"""
        import tomlkit

        path.write_text(tomlkit.dumps(data), encoding="utf-8")


# ── shell:first 与 code_plan 实现已拆分至 engines.shell_first 与 engines.code_plans ──


def parse_arguments() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Codex Agent Controller", add_help=False, allow_abbrev=False
    )
    parser.add_argument("-t", "--task", nargs="?", const="", help="Task mode")
    parser.add_argument(
        "-cp",
        "--code-plan",
        nargs="?",
        const="",
        metavar="PLAN_NAME",
        help="Code plan mode",
    )
    parser.add_argument("--list", action="store_true", help="List available tasks")
    parser.add_argument(
        "--non-interactive",
        "--non-interactively",
        action="store_true",
        dest="codex_non_interactive",
        help="Run Codex in non-interactive mode",
    )
    parser.add_argument(
        "-y",
        "--yolo",
        action="store_true",
        default=False,
        help=t("cli.help.yolo_mode"),
    )
    parser.add_argument(
        "--allow-shell-first",
        action="store_true",
        dest="allow_shell_first",
        help=(
            "Explicitly allow 'shell:first' prelaunch commands from prompt/"
            "task/code-plan files to run without a per-command confirmation "
            f"prompt. Equivalent to setting {SHELL_FIRST_ALLOW_ENV}=1. Only "
            "use this for sources you trust."
        ),
    )

    return parser.parse_known_args()


def main() -> None:
    args, extra_args = parse_arguments()
    engine = CodexEngine()
    code_plan_directories = list_code_plan_directories()

    if args.list:
        show_tasks(label="Task List", file_suffix=TASK_FILE_SUFFIX)
        if code_plan_directories:
            print()
            for idx, directory in enumerate(code_plan_directories):
                history = load_code_plan_history(directory)
                show_tasks(
                    directory=directory,
                    label=f"{directory} code plans",
                    file_suffix=CODE_PLAN_FILE_SUFFIX,
                    history=history,
                    range_selection_hint=True,
                )
                if idx < len(code_plan_directories) - 1:
                    print()
        return

    if not require_engine_cli("codex"):
        sys.exit(1)

    message, passthrough = split_passthrough(
        extra_args, CODEX_SESSION_SUBCOMMANDS | CODEX_OTHER_SUBCOMMANDS
    )

    task_prompt = handle_task_mode(args.task, file_suffix=TASK_FILE_SUFFIX)
    task_commands: list[str] = []
    if task_prompt is not None:
        if not isinstance(task_prompt, str):
            raise TypeError("Task mode returned an unexpected multi-task result")
        task_prompt, task_commands = extract_shell_first_blocks(task_prompt)
        if task_prompt:
            message = f"{message}\n\n{task_prompt}" if message else task_prompt

    code_plan_prompts: list[str] = []
    code_plan_files: list[Path] = []
    codex_non_interactive = args.codex_non_interactive
    code_plan_history: dict[str, str] | None = None

    if args.code_plan is not None:
        if not code_plan_directories:
            print("No code_plan.* directories found", file=sys.stderr)
            sys.exit(1)

        directory_from_arg, plan_argument = split_code_plan_argument(
            args.code_plan,
            code_plan_directories,
        )

        selected_directory = directory_from_arg
        plan_argument = plan_argument.strip()

        if selected_directory is None:
            if plan_argument:
                candidate_dirs = find_directories_for_plan(
                    plan_argument, code_plan_directories
                )
                if len(candidate_dirs) == 1:
                    selected_directory = candidate_dirs[0]
                elif len(candidate_dirs) > 1:
                    selected_directory = select_code_plan_directory_interactively(
                        candidate_dirs
                    )
                else:
                    selected_directory = select_code_plan_directory_interactively(
                        code_plan_directories
                    )
            else:
                selected_directory = select_code_plan_directory_interactively(
                    code_plan_directories
                )

        if selected_directory is None:
            print("Cannot determine code plan directory", file=sys.stderr)
            sys.exit(1)

        code_plan_history = load_code_plan_history(selected_directory)

        result = handle_task_mode(
            plan_argument,
            directory=selected_directory,
            label=f"Code Plan ({selected_directory})",
            file_suffix=CODE_PLAN_FILE_SUFFIX,
            history=code_plan_history,
            with_path=True,
            allow_range=True,
        )

        if isinstance(result, tuple):
            first, second = result
            if isinstance(first, list) and isinstance(second, list):
                code_plan_prompts.extend(first)
                code_plan_files.extend(second)
                if not codex_non_interactive:
                    codex_non_interactive = True
                    print("Auto-enabled non-interactive mode for code-plan range")
            else:
                prompt = cast(str, first)
                path = cast(Path, second)
                code_plan_prompts.append(prompt)
                code_plan_files.append(path)

    plan_command_sets: list[list[str]] = []
    if code_plan_prompts:
        sanitized_prompts: list[str] = []
        for prompt in code_plan_prompts:
            sanitized_prompt, commands = extract_shell_first_blocks(prompt)
            sanitized_prompts.append(sanitized_prompt)
            plan_command_sets.append(commands)
        code_plan_prompts = sanitized_prompts

    env = engine.env_manager.get_env()
    pre_launch_commands = list(task_commands)
    allow_shell_first = args.allow_shell_first or _shell_first_allowed_via_override()

    def global_setup() -> None:
        # Codex 读取用户级插件配置与安装缓存，而不是项目内 .codex/config.toml
        engine.ensure_plugins_link()
        engine.ensure_plugins_available()

    def global_teardown() -> None:
        engine.cleanup_plugins_available()
        engine.cleanup_plugins_link()

    def project_setup() -> None:
        engine.ensure_skills_link(".codex/skills")
        resolved_hooks = engine.get_hooks_to_inject()
        # Codex reads hooks from .codex/config.toml (TOML, Claude-shaped
        # matcher groups); the old .codex/settings.json was never read by it.
        engine.inject_hooks_to_settings(".codex/config.toml", resolved_hooks)
        if resolved_hooks:
            engine.warn_if_project_untrusted()

    def project_teardown() -> None:
        engine.restore_settings(".codex/config.toml")
        # 清理旧版本遗留的 .codex/settings.json —— codex 从不读取它，不清会让
        # ca doctor 一直报 "stale injections"。
        engine.restore_settings(".codex/settings.json")
        engine.cleanup_skills_link(".codex/skills")

    def launch(text: str) -> None:
        final_command = engine.build_command(
            engine.first_message(text),
            codex_non_interactive,
            yolo=args.yolo,
            passthrough=passthrough,
        )
        announce_launch(engine.name)
        try:
            engine.run_shell(final_command, env)
        finally:
            engine.cleanup_temp_prompt()

    try:
        # 全局范围用 config.toml 而不是 ~/.codex 做 key：在家目录里启动时项目
        # 范围恰好也是 ~/.codex，两者不能落进同一份登记表。
        with (
            engine.shared_injection(
                Path.home() / ".codex" / "config.toml", global_setup, global_teardown
            ),
            engine.shared_injection(
                Path.cwd() / ".codex", project_setup, project_teardown
            ),
        ):
            register_signal_handler()
            run_prelaunch_commands(
                pre_launch_commands,
                env,
                codex_non_interactive=codex_non_interactive,
                allow_override=allow_shell_first,
            )

            if code_plan_prompts:
                for prompt, file_path, plan_commands in zip(
                    code_plan_prompts,
                    code_plan_files,
                    plan_command_sets,
                    strict=False,
                ):
                    relative_plan = f"{file_path.parent.name}/{file_path.name}"
                    print(f"Code Plan: {relative_plan}")

                    run_prelaunch_commands(
                        plan_commands,
                        env,
                        codex_non_interactive=codex_non_interactive,
                        allow_override=allow_shell_first,
                    )
                    launch(f"{message}\n\n{prompt}".strip())

                    code_plan_history = update_code_plan_history(
                        file_path, code_plan_history
                    )
                    timestamp = (
                        code_plan_history.get(file_path.stem)
                        if code_plan_history
                        else None
                    )
                    if timestamp:
                        print(f"Recorded code plan run: {timestamp} ({relative_plan})")
            else:
                launch(message)
    finally:
        engine.cleanup_temp_prompt()


if __name__ == "__main__":
    main()
