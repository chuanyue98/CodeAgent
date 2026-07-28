#!/usr/bin/env python3
"""Launch Codex with dynamic prompt/skills injection and optional task/code-plan mode."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

# Ensure core modules are importable when running as a script.
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.cli_utils import require_engine_cli
from core.engine_base import BaseEngine, register_signal_handler
from core.logging_config import get_logger
from core.task_lib import (
    TASK_FILE_SUFFIX,
    get_tasks_dir,
    handle_task_mode,
    list_tasks,
    parse_range_expression,
    set_additional_template_search_paths,
    show_tasks,
)

CODE_PLAN_DIR_PATTERN = "code_plan*"
CODE_PLAN_FILE_SUFFIX = ".md"
CODE_PLAN_HISTORY_FILENAME = "history.json"
CODEX_COMMAND = "codex"
CODEX_EXEC_SUBCOMMAND = "exec"
CODEX_SKIP_PERMISSIONS_FLAG = "--dangerously-bypass-approvals-and-sandbox"
SHELL_FIRST_MARKER = "```shell:first"
# ``shell:first`` blocks let a prompt/task/code-plan markdown file specify shell
# commands that this script executes automatically before Codex launches. Those
# markdown files are not always something the current user personally wrote --
# they can come from shared code plans, downloaded skills, or marketplace
# plugins -- so this must never be silent. Setting this env var to a truthy
# value is an explicit, auditable opt-in to skip the confirmation gate (e.g.
# for trusted CI pipelines); it is off by default.
SHELL_FIRST_ALLOW_ENV = "CODEAGENT_ALLOW_SHELL_FIRST"

logger = get_logger(__name__)

set_additional_template_search_paths([Path(__file__).resolve().parent.parent])


class CodexEngine(BaseEngine):
    """Codex engine adapter using shared CodeAgent base behavior."""

    MARKETPLACE_NAME = "codeagent-local"

    def __init__(self) -> None:
        super().__init__("Codex", "codex-default")

    def build_command(self, message: str, non_interactive: bool) -> list[str]:
        if non_interactive:
            return [
                CODEX_COMMAND,
                CODEX_EXEC_SUBCOMMAND,
                CODEX_SKIP_PERMISSIONS_FLAG,
                message,
            ]

        return [
            CODEX_COMMAND,
            CODEX_SKIP_PERMISSIONS_FLAG,
            message,
        ]

    def build_chat_command(
        self, message: str, session_id: str | None = None
    ) -> list[str]:
        """Builds a headless JSON command for one ChatPage turn.

        Verified live (see docs/chatpage-cli-spike-results.md spike):
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
        except Exception:
            return tomlkit.parse("")

    def _save_config(self, path: Path, data: Any):
        """重写：支持 TOML 格式保存"""
        import tomlkit

        path.write_text(tomlkit.dumps(data), encoding="utf-8")

    def _get_codex_home(self) -> Path:
        return (Path.home() / ".codex").resolve()

    def _get_user_config_path(self) -> Path:
        return self._get_codex_home() / "config.toml"

    def _get_marketplace_root(self) -> Path:
        return (
            self._get_codex_home() / ".tmp" / "marketplaces" / self.MARKETPLACE_NAME
        ).resolve()

    def _get_plugin_cache_root(self) -> Path:
        return (
            self._get_codex_home() / "plugins" / "cache" / self.MARKETPLACE_NAME
        ).resolve()

    def _format_codex_local_path(self, path: Path) -> str:
        resolved = path.resolve()
        if os.name == "nt":
            raw = str(resolved)
            if not raw.startswith("\\\\?\\"):
                return f"\\\\?\\{raw}"
            return raw
        return resolved.as_posix()

    def _prepare_local_marketplace(self, plugins: list[dict]) -> Path:
        marketplace_root = self._get_marketplace_root()
        plugins_root = marketplace_root / "plugins"
        marketplace_plugins_dir = marketplace_root / ".agents" / "plugins"
        plugins_root.mkdir(parents=True, exist_ok=True)
        marketplace_plugins_dir.mkdir(parents=True, exist_ok=True)

        marketplace_entries: list[dict[str, Any]] = []
        for plugin_meta in plugins:
            plugin_name = plugin_meta["name"]
            plugin_src = plugin_meta.get("_plugin_dir")
            if not plugin_src:
                continue

            plugin_src_path = Path(plugin_src).resolve()
            target_link = plugins_root / plugin_name

            if target_link.exists():
                try:
                    if self._is_windows_link(target_link) or target_link.is_symlink():
                        if target_link.resolve() != plugin_src_path:
                            self._safe_remove_link(target_link)
                    else:
                        continue
                except Exception:
                    self._safe_remove_link(target_link)

            if not target_link.exists():
                self._create_skill_link(plugin_src_path, target_link)

            category = (
                plugin_meta.get("interface", {}).get("category")
                or plugin_meta.get("category")
                or "Custom"
            )
            marketplace_entries.append(
                {
                    "name": plugin_name,
                    "source": {
                        "source": "local",
                        "path": f"./plugins/{plugin_name}",
                    },
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": category,
                }
            )

        marketplace_payload = {
            "name": self.MARKETPLACE_NAME,
            "interface": {"displayName": "CodeAgent Local"},
            "plugins": marketplace_entries,
        }
        marketplace_path = marketplace_plugins_dir / "marketplace.json"
        marketplace_path.write_text(
            json.dumps(marketplace_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return marketplace_root

    def _ensure_cached_plugin_install(
        self, plugin_name: str, plugin_src_path: Path
    ) -> None:
        cache_root = self._get_plugin_cache_root() / plugin_name
        cache_root.mkdir(parents=True, exist_ok=True)
        installed_path = cache_root / "local"

        if installed_path.exists():
            try:
                if self._is_windows_link(installed_path) or installed_path.is_symlink():
                    if installed_path.resolve() == plugin_src_path.resolve():
                        return
                    self._safe_remove_link(installed_path)
                elif installed_path.is_dir():
                    shutil.rmtree(installed_path)
                else:
                    installed_path.unlink()
            except Exception:
                if installed_path.is_dir():
                    shutil.rmtree(installed_path, ignore_errors=True)
                else:
                    installed_path.unlink(missing_ok=True)

        self._create_skill_link(plugin_src_path, installed_path)

    def _format_plugins_for_settings(self, data: Any, plugins: list[dict]) -> Any:
        """实现 Codex 特有的插件注册逻辑 (marketplace + cache install + enabled 状态)"""
        import tomlkit

        marketplace_root = self._prepare_local_marketplace(plugins)

        if "marketplaces" not in data:
            data["marketplaces"] = tomlkit.table()
        if "plugins" not in data:
            data["plugins"] = tomlkit.table()

        if self.MARKETPLACE_NAME not in data["marketplaces"]:
            data["marketplaces"][self.MARKETPLACE_NAME] = tomlkit.table()
        data["marketplaces"][self.MARKETPLACE_NAME]["last_updated"] = datetime.now(
            UTC
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        data["marketplaces"][self.MARKETPLACE_NAME]["source_type"] = "local"
        data["marketplaces"][self.MARKETPLACE_NAME]["source"] = (
            self._format_codex_local_path(marketplace_root)
        )

        allowed_plugin_ids = {
            f"{plugin_meta['name']}@{self.MARKETPLACE_NAME}" for plugin_meta in plugins
        }
        for ext_id in list(data["plugins"].keys()):
            if (
                ext_id.endswith(f"@{self.MARKETPLACE_NAME}")
                and ext_id not in allowed_plugin_ids
            ):
                if isinstance(data["plugins"][ext_id], dict):
                    data["plugins"][ext_id]["enabled"] = False

        for plugin_meta in plugins:
            plugin_name = plugin_meta["name"]
            plugin_src = plugin_meta.get("_plugin_dir")
            if not plugin_src:
                continue

            self._ensure_cached_plugin_install(plugin_name, Path(plugin_src).resolve())
            ext_id = f"{plugin_name}@{self.MARKETPLACE_NAME}"

            if ext_id not in data["plugins"]:
                data["plugins"][ext_id] = tomlkit.table()

            data["plugins"][ext_id]["enabled"] = True

        return data

    def ensure_plugins_available(self) -> None:
        plugins = self.get_plugins_to_mount()
        if not plugins:
            return

        config_path = self._get_user_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # 备份全局配置。不再依赖 ``not backup_path.exists()`` 仅首次创建：
        # 每次都刷新备份（覆盖旧的），确保即使上一轮崩溃导致备份缺失也能
        # 重新建立。但若 config 已带有本工具的注入痕迹（说明上次崩溃未还
        # 原），则保留现有干净备份，避免把脏 config 覆盖掉干净备份导致后续
        # 永久无法还原。
        backup_path = config_path.with_suffix(".toml.bak")
        if config_path.exists():
            try:
                current_content = config_path.read_text(encoding="utf-8")
            except Exception:
                current_content = ""
            if self.MARKETPLACE_NAME not in current_content:
                shutil.copy2(config_path, backup_path)
                logger.info("Created safety backup of global config: %s", backup_path.name)

        data = self._load_config(config_path)
        data = self._format_plugins_for_settings(data, plugins)
        self._save_config(config_path, data)
        logger.info("Registered Codex plugins in %s", config_path)

    def cleanup_plugins_available(self) -> None:
        """还原全局配置并清理临时市场/缓存"""
        config_path = self._get_user_config_path()
        backup_path = config_path.with_suffix(".toml.bak")

        if backup_path.exists():
            # 使用 copy 而非 move(os.replace) 还原，保留备份副本，确保下一轮
            # 仍可从干净备份还原（即使本轮再次崩溃）。
            shutil.copy2(str(backup_path), str(config_path))
            logger.info("Restored global config.toml from backup")
        elif config_path.exists():
            # 如果没有备份但文件存在，检查是否由 CodeAgent 创建
            try:
                content = config_path.read_text(encoding="utf-8")
                if self.MARKETPLACE_NAME in content:
                    config_path.unlink()
                    logger.info("Removed temporary global config.toml")
            except Exception:
                pass

        # 清理临时市场目录
        marketplace_root = self._get_marketplace_root()
        if marketplace_root.exists():
            # 仅在非 Linux 或确认是链接时移除 plugins 链接，避免 rmtree 报错
            plugins_link = marketplace_root / "plugins"
            if plugins_link.exists() and (
                self._is_windows_link(plugins_link) or plugins_link.is_symlink()
            ):
                self._safe_remove_link(plugins_link)
            shutil.rmtree(marketplace_root, ignore_errors=True)

        # 清理插件缓存 (CodeAgent 专有部分)
        cache_root = self._get_plugin_cache_root()
        if cache_root.exists():
            shutil.rmtree(cache_root, ignore_errors=True)
            logger.info("Cleaned up local Codex plugin cache")


def extract_shell_first_blocks(text: str) -> tuple[str, list[str]]:
    """Extract and remove shell:first blocks, returning text and commands."""
    if not text:
        return text, []

    commands: list[str] = []
    lines = text.splitlines()
    sanitized_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.strip() == SHELL_FIRST_MARKER:
            i += 1
            block_lines: list[str] = []
            while i < len(lines) and lines[i].strip() != "```":
                block_lines.append(lines[i])
                i += 1
            if i == len(lines):
                sanitized_lines.append(line)
                sanitized_lines.extend(block_lines)
                break
            script = "\n".join(block_lines).strip()
            if script:
                commands.append(script)
            i += 1
            continue

        sanitized_lines.append(line)
        i += 1

    sanitized = "\n".join(sanitized_lines).strip()
    return sanitized, commands


def _shell_first_allowed_via_override() -> bool:
    """Checks the explicit opt-in env var that skips the shell:first confirmation gate."""
    return os.environ.get(SHELL_FIRST_ALLOW_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def run_prelaunch_commands(
    commands: list[str],
    env: dict,
    codex_non_interactive: bool = False,
    allow_override: bool | None = None,
) -> None:
    """Run shell:first commands before invoking Codex.

    These commands come from markdown text (prompts/tasks/code plans) that may
    originate from shared files, downloaded skills, or marketplace plugins --
    not necessarily something the current user wrote or reviewed. This must
    never execute silently:

    - Non-interactive / no-TTY sessions fail closed: they refuse to run
      shell:first commands unless ``SHELL_FIRST_ALLOW_ENV`` is explicitly set.
    - Interactive sessions print the full command text and require a "y"
      confirmation before each command runs.
    """
    if not commands:
        return

    allow_override = (
        _shell_first_allowed_via_override()
        if allow_override is None
        else allow_override
    )
    interactive = (
        sys.stdin.isatty() and sys.stdout.isatty() and not codex_non_interactive
    )

    print()
    print(
        "⚠️  This prompt/task/code-plan file contains 'shell:first' "
        "command(s) that would run automatically on this machine before "
        "Codex launches."
    )
    print(
        "⚠️  Only proceed if you trust where this file came from -- "
        "shared code plans, skills, and plugins can embed arbitrary shell "
        "commands."
    )

    if not interactive and not allow_override:
        print(
            "❌ Refusing to run shell:first commands in a non-interactive "
            f"session. Re-run interactively, or set {SHELL_FIRST_ALLOW_ENV}=1 "
            "(or pass --allow-shell-first) to explicitly allow this.",
            file=sys.stderr,
        )
        for script in commands:
            command = script.strip()
            if not command:
                continue
            preview = command.splitlines()[0]
            suffix = " ..." if "\n" in command else ""
            print(f"    would run: {preview}{suffix}", file=sys.stderr)
        sys.exit(1)

    if allow_override:
        print(
            f"✅ {SHELL_FIRST_ALLOW_ENV} override active -- running "
            "shell:first commands without per-command confirmation."
        )

    for script in commands:
        command = script.strip()
        if not command:
            continue

        print("----- shell:first command -----")
        print(command)
        print("--------------------------------")

        if interactive and not allow_override:
            answer = input("Run this command? [y/N]: ").strip().lower()
            if answer not in ("y", "yes"):
                print("Skipped by user.")
                continue

        preview = command.splitlines()[0]
        suffix = " ..." if "\n" in command else ""
        print(f"Running prelaunch command: {preview}{suffix}")

        try:
            if os.name == "nt":
                shell = shutil.which("pwsh", path=env.get("PATH")) or shutil.which(
                    "powershell", path=env.get("PATH")
                )
                if not shell:
                    print(
                        "No PowerShell executable found for shell:first",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                subprocess.run(
                    [shell, "-NoProfile", "-Command", command],
                    check=True,
                    env=env,
                )
            else:
                shell = shutil.which("bash", path=env.get("PATH")) or shutil.which(
                    "sh", path=env.get("PATH")
                )
                if not shell:
                    print("No POSIX shell found for shell:first", file=sys.stderr)
                    sys.exit(1)
                shell_args = (
                    [shell, "-lc", command]
                    if Path(shell).name == "bash"
                    else [shell, "-c", command]
                )
                subprocess.run(
                    shell_args,
                    check=True,
                    env=env,
                )
        except subprocess.CalledProcessError as exc:
            print(f"Prelaunch command failed: {exc}", file=sys.stderr)
            sys.exit(1)


def get_code_plan_history_path(directory: str | Path) -> Path:
    return get_tasks_dir(directory) / CODE_PLAN_HISTORY_FILENAME


def load_code_plan_history(directory: str | Path) -> dict[str, str]:
    history_path = get_code_plan_history_path(directory)

    if not history_path.exists():
        return {}

    try:
        with open(history_path, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(key): str(value) for key, value in data.items()}
    except json.JSONDecodeError as exc:
        print(f"Failed to parse code plan history: {exc}", file=sys.stderr)

    return {}


def save_code_plan_history(directory: str | Path, history: dict[str, str]) -> None:
    history_path = get_code_plan_history_path(directory)
    history_path.parent.mkdir(parents=True, exist_ok=True)

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def update_code_plan_history(
    plan_file: Path,
    history: dict[str, str] | None = None,
) -> dict[str, str]:
    directory = plan_file.parent

    if history is None:
        history = load_code_plan_history(directory)

    history[plan_file.stem] = datetime.now().isoformat(timespec="seconds")
    save_code_plan_history(directory, history)
    return history


def list_code_plan_directories(pattern: str = CODE_PLAN_DIR_PATTERN) -> list[str]:
    script_dir = Path(__file__).resolve().parent
    directories = [path.name for path in script_dir.glob(pattern) if path.is_dir()]
    return sorted(directories)


def split_code_plan_argument(
    argument: str,
    directories: list[str],
) -> tuple[str | None, str]:
    trimmed = argument.strip()

    if not trimmed:
        return None, ""

    if trimmed in directories:
        return trimmed, ""

    for separator in (":", "/"):
        if separator in trimmed:
            dir_candidate, plan_part = trimmed.split(separator, 1)
            dir_candidate = dir_candidate.strip()
            plan_part = plan_part.strip()
            if dir_candidate in directories:
                return dir_candidate, plan_part

    return None, trimmed


def find_directories_for_plan(plan_name: str, directories: list[str]) -> list[str]:
    normalized = plan_name.strip()
    if not normalized:
        return []

    if parse_range_expression(normalized) is not None:
        return directories.copy()

    if normalized.endswith(CODE_PLAN_FILE_SUFFIX):
        normalized = normalized[: -len(CODE_PLAN_FILE_SUFFIX)]

    matches: list[str] = []

    for directory in directories:
        plans = list_tasks(directory, file_suffix=CODE_PLAN_FILE_SUFFIX)
        if normalized in plans:
            matches.append(directory)

    return matches


def select_code_plan_directory_interactively(directories: list[str]) -> str:
    print("Available code plan directories:")
    for i, directory in enumerate(directories, 1):
        print(f"  {i}. {directory}")

    while True:
        choice = input("Choose directory by index or name: ").strip()
        if not choice:
            print("Input cannot be empty")
            continue

        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(directories):
                return directories[index]
            print(f"Index out of range (1-{len(directories)})")
            continue

        if choice in directories:
            return choice

        print(f"Directory not found: {choice}")


def parse_arguments() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="Codex Agent Controller")
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
        default=True,
        help="开启 YOLO 模式 (默认开启)",
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

    full_prompt = engine.assemble_prompt(task=" ".join(extra_args).strip() or None)
    full_prompt, general_commands = extract_shell_first_blocks(full_prompt)

    task_prompt = handle_task_mode(args.task, file_suffix=TASK_FILE_SUFFIX)
    task_commands: list[str] = []
    if task_prompt is not None:
        if not isinstance(task_prompt, str):
            raise TypeError("Task mode returned an unexpected multi-task result")
        task_prompt, task_commands = extract_shell_first_blocks(task_prompt)
        if task_prompt:
            full_prompt = (
                f"{full_prompt}\n\n{task_prompt}" if full_prompt else task_prompt
            )

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
    pre_launch_commands = list(general_commands) + list(task_commands)
    allow_shell_first = args.allow_shell_first or _shell_first_allowed_via_override()

    resource_lock = engine.acquire_resource_lock(
        Path.home() / ".codex" / ".codeagent-session.lock"
    )
    try:
        engine.ensure_skills_link(".codex/skills")
        # 挂载插件 (创建全局临时映射以满足 Codex 加载要求)
        engine.ensure_plugins_link()

        # 注入动态钩子
        resolved_hooks = engine.get_hooks_to_inject()
        engine.inject_hooks_to_settings(".codex/settings.json", resolved_hooks)

        # Codex 读取用户级插件配置与安装缓存，而不是项目内 .codex/config.toml
        engine.ensure_plugins_available()

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

                message = full_prompt
                if prompt:
                    message = f"{message}\n\n{prompt}" if message else prompt

                run_prelaunch_commands(
                    plan_commands,
                    env,
                    codex_non_interactive=codex_non_interactive,
                    allow_override=allow_shell_first,
                )

                concise_msg = engine.write_temp_prompt(message)
                try:
                    final_command = engine.build_command(
                        concise_msg, codex_non_interactive
                    )
                    print(f"Launching {engine.name}...")
                    engine.run_shell(final_command, env)
                finally:
                    engine.cleanup_temp_prompt()

                code_plan_history = update_code_plan_history(
                    file_path, code_plan_history
                )
                timestamp = (
                    code_plan_history.get(file_path.stem) if code_plan_history else None
                )
                if timestamp:
                    print(f"Recorded code plan run: {timestamp} ({relative_plan})")
        else:
            concise_msg = engine.write_temp_prompt(full_prompt)
            try:
                final_command = engine.build_command(concise_msg, codex_non_interactive)
                print(f"Launching {engine.name}...")
                engine.run_shell(final_command, env)
            finally:
                engine.cleanup_temp_prompt()
    finally:
        try:
            # 1. 还原配置到注入前状态
            engine.restore_settings(".codex/settings.json")
            # 2. 还原全局 config.toml 并清理缓存
            engine.cleanup_plugins_available()
            # 3. 清理插件链接，避免 ~/.codex/plugins/ 下符号链接泄漏
            engine.cleanup_plugins_link()
            # 4. 清理所有技能链接
            engine.cleanup_skills_link(".codex/skills")
            # 5. 兜底清理所有临时文件
            engine.cleanup_temp_prompt()
        finally:
            engine.release_resource_lock(resource_lock)


if __name__ == "__main__":
    main()
