"""Language resolution and the message table for user-facing CLI output.

Before this module, ``config.json`` carried a ``language`` field that nothing
read, and user-facing output was a mix of English and Chinese — English help
text and health checks, Chinese first-run prompts. This makes the setting real.

Resolution order, first match wins:

1. ``CA_LANG`` environment variable — lets a single invocation override
   everything, and is how the launcher passes its choice to the engine
   subprocesses so both halves of a session speak the same language.
2. ``language`` in ``config.json``.
3. The OS locale.
4. English.

Engines run as separate processes, so resolution is lazy and self-contained:
calling :func:`t` from anywhere works without the caller plumbing a language
through.
"""

from __future__ import annotations

import locale
import os
from typing import Any

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "zh")

# Legacy value from the era when the setting was inert; treat it as "decide
# for me" rather than failing on a config people already have on disk.
_AUTO_VALUES = {"", "auto", "hybrid", "system", None}

ENV_VAR = "CA_LANG"

_resolved: str | None = None


def _normalize(value: str | None) -> str | None:
    """Maps a user-supplied language value onto a supported code, or None."""
    if value is None:
        return None
    candidate = value.strip().lower().replace("_", "-")
    if candidate in _AUTO_VALUES:
        return None
    if candidate in SUPPORTED_LANGUAGES:
        return candidate
    # Accept locale-ish forms such as zh-CN, zh-Hans, en-US.
    prefix = candidate.split("-")[0]
    if prefix in SUPPORTED_LANGUAGES:
        return prefix
    return None


def _from_config() -> str | None:
    try:
        import json

        from core.resource_locator import CODE_ROOT, get_default_config_path

        path = get_default_config_path(CODE_ROOT)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _normalize(data.get("language")) if isinstance(data, dict) else None


def _from_locale() -> str | None:
    # locale.getdefaultlocale() is deprecated and slated for removal in 3.15,
    # and locale.getlocale() reports the C locale until setlocale() is called,
    # so consult the standard environment variables first.
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            normalized = _normalize(value.split(".")[0].split(":")[0])
            if normalized:
                return normalized
    try:
        code = locale.getlocale()[0]
    except Exception:
        return None
    return _normalize(code)


def resolve_language() -> str:
    """Returns the active language, resolving and caching it on first use."""
    global _resolved
    if _resolved is None:
        _resolved = (
            _normalize(os.environ.get(ENV_VAR))
            or _from_config()
            or _from_locale()
            or DEFAULT_LANGUAGE
        )
    return _resolved


def set_language(value: str | None) -> str | None:
    """Overrides the active language.

    Pass ``None`` to clear the cache so the next :func:`t` call resolves
    afresh. Clearing deliberately does *not* resolve immediately — doing so
    would re-cache from the current environment, defeating the reset.
    """
    global _resolved
    _resolved = _normalize(value)
    return _resolved


MESSAGES: dict[str, dict[str, str]] = {
    # --- first-run project registration ---
    "project.unregistered_hint": {
        "en": (
            "i  {cwd} is not registered to a resource group; "
            "running with defaults.\n"
            "   To register: ca project add {cwd} --group <group-name>"
        ),
        "zh": (
            "i  {cwd} 尚未注册到任何资源组，本次将使用默认设置运行。\n"
            "   如需注册: ca project add {cwd} --group <group-name>"
        ),
    },
    "project.unregistered_title": {
        "en": "\n[*] Current directory is not registered to a resource group: {cwd}",
        "zh": "\n[*] 当前目录尚未注册到任何资源组: {cwd}",
    },
    "project.pick_group": {
        "en": "Pick a resource group (future launches here load it automatically):",
        "zh": "请选择要绑定的资源组 (以后从这个目录启动会自动加载对应技能集):",
    },
    "project.new_group_option": {
        "en": "  n. Create a new group",
        "zh": "  n. 新建资源组",
    },
    "project.skip_option": {
        "en": "  <enter>. Skip (use defaults this time, nothing written)",
        "zh": "  直接回车. 跳过 (本次使用默认组, 不写入配置)",
    },
    "project.new_group_prompt": {
        "en": "New group name: ",
        "zh": "新组名称: ",
    },
    "project.no_group_name": {
        "en": "[!] No group name entered; skipping registration.",
        "zh": "[!] 未输入组名, 跳过注册。",
    },
    "project.invalid_choice": {
        "en": "[!] Invalid input; skipping registration.",
        "zh": "[!] 无效输入, 跳过注册。",
    },
    "project.registered": {
        "en": "[OK] Registered the current directory to group [{group}]\n",
        "zh": "[OK] 已将当前目录注册到组 [{group}]\n",
    },
    # --- proxy ---
    "proxy.enabled": {
        "en": "Proxy enabled: {scheme}://{host}:{port}",
        "zh": "代理已启用: {scheme}://{host}:{port}",
    },
    # --- new task authoring ---
    "task.authoring_start": {
        "en": "Starting the task-authoring expert to draft: {name}...",
        "zh": "启动任务编排专家为您编写新任务: {name}...",
    },
    "task.target_location": {
        "en": "Target location: {path}",
        "zh": "目标位置: {path}",
    },
    "task.authoring_prompt": {
        "en": (
            "Enter 'Task Authoring' mode. Write a new automation task playbook "
            "for CodeAgent, in the file named: "
        ),
        "zh": (
            "请启动'任务编排专家 (Task Authoring)'模式，目标是为 CodeAgent "
            "编写一个新的自动化任务剧本，文件名为："
        ),
    },
    # --- engine argparse help ---
    "cli.help.task_mode": {"en": "Task mode", "zh": "任务模式"},
    "cli.help.list_tasks": {"en": "List all tasks", "zh": "列出所有任务"},
    "cli.help.non_interactive": {
        "en": "Non-interactive mode",
        "zh": "非交互模式",
    },
    "cli.help.yolo_default_on": {
        "en": "YOLO mode (on by default)",
        "zh": "开启 YOLO 模式 (默认开启)",
    },
    "cli.help.review_pr_url": {
        "en": "PR URL to review",
        "zh": "代码审查 PR URL",
    },
    # --- config / engine selection ---
    "config.seeded": {
        "en": "Created {path} from the bundled template (first launch)",
        "zh": "已根据内置模板创建 {path} (首次启动)",
    },
    "config.load_failed": {
        "en": "[!] Warning: Failed to load config.json: {error}",
        "zh": "[!] 警告: 加载 config.json 失败: {error}",
    },
    "engine.unknown_default": {
        "en": (
            "[!] Unknown default_engine {value!r} in config.json; "
            "falling back to {fallback}.\n"
            "    Known engines: {known}"
        ),
        "zh": (
            "[!] config.json 中的 default_engine {value!r} 无法识别，"
            "本次回退到 {fallback}。\n"
            "    可用引擎: {known}"
        ),
    },
    "engine.yolo_warning": {
        "en": (
            "[!] YOLO mode is ON: the engine may edit files and run commands "
            "without asking for approval."
        ),
        "zh": "[!] YOLO 模式已开启: 引擎可能不经确认就修改文件、执行命令。",
    },
    # --- ca ui ---
    "ui.open_in_browser": {
        "en": "Open the UI in your browser: {url}",
        "zh": "请在浏览器中打开: {url}",
    },
    "ui.missing_dependency": {
        "en": (
            "[X] Missing dependency for 'ca ui': {module}\n"
            "Install project dependencies first:\n"
            "  uv sync\n"
            "or:\n"
            "  pip install -e ."
        ),
        "zh": (
            "[X] 运行 'ca ui' 缺少依赖: {module}\n"
            "请先安装项目依赖:\n"
            "  uv sync\n"
            "或:\n"
            "  pip install -e ."
        ),
    },
    "ui.vite_starting": {
        "en": "Starting Vite dev server at http://{host}:{port} ...",
        "zh": "正在启动 Vite 开发服务器 http://{host}:{port} ...",
    },
    "ui.vite_failed_fallback": {
        "en": "[!] Failed to start Vite dev server; falling back to built UI.",
        "zh": "[!] Vite 开发服务器启动失败，回退到已构建的界面。",
    },
    "ui.vite_failed_no_dist": {
        "en": (
            "[X] Failed to start Vite dev server, and no built UI was found.\n"
            "Install frontend deps in web/frontend and retry."
        ),
        "zh": (
            "[X] Vite 开发服务器启动失败，且找不到已构建的界面。\n"
            "请先在 web/frontend 安装前端依赖后重试。"
        ),
    },
    "ui.vite_detected": {
        "en": "Detected Vite dev server at {url}",
        "zh": "检测到 Vite 开发服务器: {url}",
    },
    "ui.api_starting": {
        "en": "Starting Web UI API at http://127.0.0.1:{port} ...",
        "zh": "正在启动 Web UI 接口服务 http://127.0.0.1:{port} ...",
    },
    "ui.not_built": {
        "en": (
            "[X] The Web UI has not been built yet (expected {index_path}).\n"
            "\n"
            "Build it once with:\n"
            "  cd {frontend_root}\n"
            "  bun install && bun run build      # or: npm install && npm run build\n"
            "\n"
            "Then run `ca ui` again. For live-reloading frontend work, set "
            "CA_UI_DEV=1 instead to have `ca ui` manage a Vite dev server."
        ),
        "zh": (
            "[X] Web UI 尚未构建 (期望文件: {index_path})。\n"
            "\n"
            "只需构建一次:\n"
            "  cd {frontend_root}\n"
            "  bun install && bun run build      # 或: npm install && npm run build\n"
            "\n"
            "然后重新运行 `ca ui`。如果需要前端热更新开发，改为设置 "
            "CA_UI_DEV=1，让 `ca ui` 托管 Vite 开发服务器。"
        ),
    },
    "ui.starting": {
        "en": "Starting Web UI at {url}...",
        "zh": "正在启动 Web UI: {url}...",
    },
    # --- ca history ---
    "history.none": {
        "en": "No sessions found for this project.",
        "zh": "当前项目没有找到任何会话。",
    },
    "history.found": {
        "en": "Found {count} session(s) for {path}:\n",
        "zh": "在 {path} 找到 {count} 个会话:\n",
    },
    "history.show_hint": {
        "en": "\nUse: ca history show <engine> <session_id>",
        "zh": "\n查看详情: ca history show <engine> <session_id>",
    },
    "history.not_found": {
        "en": "[X] Session not found: {engine}/{session_id}",
        "zh": "[X] 未找到会话: {engine}/{session_id}",
    },
    "history.field_engine": {"en": "Engine:  ", "zh": "引擎:    "},
    "history.field_session": {"en": "Session: ", "zh": "会话:    "},
    "history.field_started": {"en": "Started: ", "zh": "开始于:  "},
    "history.field_messages": {"en": "Messages:", "zh": "消息数:  "},
    "history.field_model": {"en": "Model:   ", "zh": "模型:    "},
    "history.unknown_model": {"en": "(unknown)", "zh": "(未知)"},
    "history.no_title": {"en": "(no title)", "zh": "(无标题)"},
    "history.role_user": {"en": "USER", "zh": "用户"},
    "history.role_assistant": {"en": "ASSISTANT", "zh": "助手"},
    # --- ca history convert ---
    "convert.about_to": {
        "en": "About to convert a session (the source session is left untouched):",
        "zh": "即将转换会话 (源会话不会被修改):",
    },
    "convert.line_source": {
        "en": "  Source: {engine}/{session_id}  ({count} msgs)",
        "zh": "  来源: {engine}/{session_id}  (共 {count} 条消息)",
    },
    "convert.line_title": {"en": "  Title:  {title}", "zh": "  标题: {title}"},
    "convert.line_target": {"en": "  Target: {engine}", "zh": "  目标: {engine}"},
    "convert.needs_confirmation": {
        "en": (
            "[X] Refusing to convert without confirmation in a non-interactive "
            "session. Re-run with --yes to skip this prompt."
        ),
        "zh": (
            "[X] 非交互环境下不会在未确认时执行转换。请加上 --yes 重新运行以跳过确认。"
        ),
    },
    "convert.confirm": {
        "en": "Proceed with conversion?",
        "zh": "确认执行转换?",
    },
    "convert.cancelled": {"en": "Cancelled.", "zh": "已取消。"},
    "convert.done": {
        "en": "[OK] Converted {source} -> {target}",
        "zh": "[OK] 已转换 {source} -> {target}",
    },
    "convert.new_id": {
        "en": "   New session ID: {session_id}",
        "zh": "   新会话 ID: {session_id}",
    },
    "convert.resume_claude": {
        "en": "   Resume with: claude -r {session_id}",
        "zh": "   恢复方式: claude -r {session_id}",
    },
    "convert.resume_codex": {
        "en": "   Resume with: codex continue",
        "zh": "   恢复方式: codex continue",
    },
    "convert.resume_gemini": {
        "en": "   Resume with: gemini (select from history)",
        "zh": "   恢复方式: gemini (从历史记录中选择)",
    },
    "convert.resume_opencode": {
        "en": "   Resume with: opencode (select from history)",
        "zh": "   恢复方式: opencode (从历史记录中选择)",
    },
    "convert.failed": {
        "en": "[X] Conversion failed: {error}",
        "zh": "[X] 转换失败: {error}",
    },
    # --- ca ps / ca stop ---
    "ps.none_running": {"en": "No running tasks.", "zh": "没有正在运行的任务。"},
    "ps.none_tracked": {"en": "No tracked task runs.", "zh": "没有已记录的任务运行。"},
    "ps.hint": {
        "en": (
            "\nUse `ca stop <task id>` to terminate one, "
            "or `ca ps --all` to see recent history."
        ),
        "zh": "\n使用 `ca stop <task id>` 终止某个任务，或 `ca ps --all` 查看历史记录。",
    },
    "stop.not_found": {
        "en": "[X] No such task run: {task_id}",
        "zh": "[X] 没有这个任务运行记录: {task_id}",
    },
    "stop.list_hint": {
        "en": "   Use `ca ps --all` to see known task ids.",
        "zh": "   使用 `ca ps --all` 查看已知的任务 id。",
    },
    "stop.not_running": {
        "en": "[!] Task {task_id} is not running (status: {status}).",
        "zh": "[!] 任务 {task_id} 并未在运行 (状态: {status})。",
    },
    "stop.stopped": {"en": "[OK] Stopped {task_id}", "zh": "[OK] 已停止 {task_id}"},
    "stop.failed": {
        "en": "[X] Failed to stop {task_id}",
        "zh": "[X] 停止 {task_id} 失败",
    },
    # --- ca batch-run ---
    "batch.no_projects": {
        "en": "[X] No registered projects{scope} found in project_registry.",
        "zh": "[X] project_registry 中没有{scope}已注册的项目。",
    },
    "batch.scope_group": {"en": " in group '{group}'", "zh": "属于组 '{group}' 的"},
    "batch.no_task": {
        "en": "[X] No such task: {task} (looked in {root})",
        "zh": "[X] 没有这个任务: {task} (查找路径: {root})",
    },
    "batch.plan_header": {
        "en": "{count} project(s) will run '{task}' with {engine}:",
        "zh": "将有 {count} 个项目使用 {engine} 运行 '{task}':",
    },
    "batch.plan_row": {
        "en": "  - {path}  (group: {group})",
        "zh": "  - {path}  (组: {group})",
    },
    "batch.dry_run": {
        "en": "\n(dry run — nothing started)",
        "zh": "\n(演练模式 — 未启动任何任务)",
    },
    "batch.started_row": {
        "en": "  [OK] started {task_id}  ({workspace})",
        "zh": "  [OK] 已启动 {task_id}  ({workspace})",
    },
    "batch.skipped_row": {
        "en": "  [--] skipped, already running  ({workspace})",
        "zh": "  [--] 已跳过，任务正在运行中  ({workspace})",
    },
    "batch.failed_row": {
        "en": "  [X] failed: {reason}  ({workspace})",
        "zh": "  [X] 失败: {reason}  ({workspace})",
    },
    "batch.summary": {
        "en": "\n{started} started, {skipped} skipped, {failed} failed.",
        "zh": "\n已启动 {started} 个，跳过 {skipped} 个，失败 {failed} 个。",
    },
    "batch.track_hint": {
        "en": "Use `ca ps` to track progress, `ca stop <task_id>` to cancel one.",
        "zh": "使用 `ca ps` 跟踪进度，`ca stop <task_id>` 取消某个任务。",
    },
    # --- ca project ---
    "project.not_a_directory": {
        "en": "[X] Not a directory: {path}",
        "zh": "[X] 不是一个目录: {path}",
    },
    "project.group_missing": {
        "en": (
            "[!] Group '{group}' doesn't exist yet in config.json's groups — "
            "the project will register, but won't have any skills/prompts/hooks "
            "mounted until the group is created (e.g. via the Web UI's Config Hub)."
        ),
        "zh": (
            "[!] config.json 的 groups 中还没有 '{group}' 这个组 —— "
            "项目仍会注册成功，但在该组创建之前不会挂载任何技能/提示词/钩子 "
            "(可通过 Web UI 的 Config Hub 创建)。"
        ),
    },
    "project.add_ok": {
        "en": "[OK] Registered {path} -> group '{group}'",
        "zh": "[OK] 已注册 {path} -> 组 '{group}'",
    },
    "project.registry_size": {
        "en": "   project_registry now has {count} entries.",
        "zh": "   project_registry 现有 {count} 条记录。",
    },
    "project.remove_missing": {
        "en": "[!] {path} was not found in project_registry.",
        "zh": "[!] project_registry 中找不到 {path}。",
    },
    "project.removed": {
        "en": "[OK] Removed {path} from project_registry.",
        "zh": "[OK] 已从 project_registry 移除 {path}。",
    },
    "project.none_registered": {
        "en": "No projects registered.",
        "zh": "尚未注册任何项目。",
    },
    "project.list_row": {
        "en": "  {mark}  {path}  (group: {group})",
        "zh": "  {mark}  {path}  (组: {group})",
    },
    "project.missing_marker": {"en": "x (missing)", "zh": "x (已丢失)"},
    # --- ca resources ---
    "resources.none": {"en": "No {kind} found.", "zh": "没有找到任何{kind}。"},
    "resources.header": {
        "en": "{kind} ({count}) — {label}",
        "zh": "{kind} ({count}) — {label}",
    },
    "resources.label_active": {"en": "active", "zh": "已生效"},
    "resources.label_enabled_in": {
        "en": "enabled in '{group}'",
        "zh": "在 '{group}' 中已启用",
    },
    # --- ca mcp ---
    "mcp.bad_env_pair": {
        "en": "[X] --env expects KEY=VALUE, got: {pair}",
        "zh": "[X] --env 需要 KEY=VALUE 格式，收到: {pair}",
    },
    "mcp.error": {"en": "[X] {error}", "zh": "[X] {error}"},
    "mcp.added": {
        "en": "[OK] Added '{name}' to {engine} ({scope} scope)",
        "zh": "[OK] 已将 '{name}' 添加到 {engine} ({scope}作用域)",
    },
    "mcp.scope_project": {"en": "project", "zh": "项目级"},
    "mcp.scope_global": {"en": "global", "zh": "全局"},
    "mcp.sync_hint": {
        "en": "   Copy it to the others with: ca mcp sync {engine}",
        "zh": "   同步到其他引擎: ca mcp sync {engine}",
    },
    "mcp.sync_targets": {
        "en": "   (targets: {targets})",
        "zh": "   (目标引擎: {targets})",
    },
    "mcp.not_found": {
        "en": "[X] No such MCP server in {engine}: {name}",
        "zh": "[X] {engine} 中没有这个 MCP 服务: {name}",
    },
    "mcp.removed": {
        "en": "[OK] Removed '{name}' from {engine}",
        "zh": "[OK] 已从 {engine} 移除 '{name}'",
    },
    "mcp.nothing_to_sync": {
        "en": "Nothing to sync — {source} has no MCP servers configured.",
        "zh": "无需同步 —— {source} 没有配置任何 MCP 服务。",
    },
    "mcp.dry_run": {
        "en": "Dry run — nothing was written.",
        "zh": "演练模式 —— 未写入任何内容。",
    },
    "mcp.partial_failure": {
        "en": "\n[!] {failed} of {total} operations failed.",
        "zh": "\n[!] {total} 项操作中有 {failed} 项失败。",
    },
    # --- ca doctor ---
    # Section titles and check labels are translated alongside details and fix
    # hints: a health report that mixes a Chinese hint under an English label
    # is the same half-done feel the language setting exists to remove.
    "doctor.title": {"en": "CodeAgent Health Check", "zh": "CodeAgent 健康检查"},
    "doctor.mode_dry_run": {
        "en": "--dry-run mode: previewing what --fix would change; nothing is applied",
        "zh": "--dry-run 模式: 仅预览 --fix 会做的改动，不会实际执行",
    },
    "doctor.mode_fix": {
        "en": "--fix mode: auto-repairable issues will be resolved",
        "zh": "--fix 模式: 将自动修复可修复的问题",
    },
    "doctor.section_runtime": {"en": "Runtime", "zh": "运行环境"},
    "doctor.section_configuration": {"en": "Configuration", "zh": "配置"},
    "doctor.section_context": {"en": "Context Resolution", "zh": "上下文解析"},
    "doctor.section_environment": {"en": "Environment", "zh": "环境"},
    "doctor.section_parity": {"en": "Cross-Engine Parity", "zh": "跨引擎一致性"},
    "doctor.section_sessions": {"en": "Session Integrity", "zh": "会话完整性"},
    "doctor.result_failures": {
        "en": (
            "  Result: {failures} failure(s), {warnings} warning(s) — "
            "run 'ca doctor --fix' for auto-repairs"
        ),
        "zh": (
            "  结果: {failures} 项失败，{warnings} 项警告 —— "
            "运行 'ca doctor --fix' 可自动修复"
        ),
    },
    "doctor.result_warnings": {
        "en": "  Result: {warnings} warning(s) — check the hints above",
        "zh": "  结果: {warnings} 项警告 —— 请查看上方提示",
    },
    "doctor.result_ok": {
        "en": "  Result: all checks passed",
        "zh": "  结果: 全部检查通过",
    },
    # runtime
    "doctor.python_too_old": {
        "en": "CodeAgent requires Python 3.13+",
        "zh": "CodeAgent 需要 Python 3.13+",
    },
    "doctor.python_upgrade": {"en": "Upgrade Python", "zh": "请升级 Python"},
    "doctor.python_unsupported": {
        "en": "Unsupported Python version",
        "zh": "不支持的 Python 版本",
    },
    "doctor.python_upgrade_to": {
        "en": "Upgrade to Python 3.13+",
        "zh": "请升级到 Python 3.13+",
    },
    "doctor.engine_label": {"en": "Engine: {engine}", "zh": "引擎: {engine}"},
    "doctor.engine_missing": {
        "en": "binary not found in PATH",
        "zh": "PATH 中找不到可执行文件",
    },
    # configuration
    "doctor.config_not_found": {"en": "file not found", "zh": "文件不存在"},
    "doctor.config_run_fix": {
        "en": "Run: ca doctor --fix  (seeds config.json from config.example.json)",
        "zh": "运行: ca doctor --fix  (从 config.example.json 生成 config.json)",
    },
    "doctor.config_seeded": {
        "en": "  Created {path} from the bundled template",
        "zh": "  已根据内置模板创建 {path}",
    },
    "doctor.config_unparsable": {
        "en": "failed to load or parse configuration",
        "zh": "配置加载或解析失败",
    },
    "doctor.config_valid": {"en": "valid configuration", "zh": "配置有效"},
    "doctor.dir_subdirs": {"en": "{count} subdirectories", "zh": "{count} 个子目录"},
    "doctor.dir_missing": {"en": "directory not found", "zh": "目录不存在"},
    # context resolution
    "doctor.active_group": {
        "en": "Active project group: {group}",
        "zh": "当前项目资源组: {group}",
    },
    "doctor.skill_scanner": {"en": "Skill Scanner", "zh": "技能扫描器"},
    "doctor.hook_scanner": {"en": "Hook Scanner", "zh": "钩子扫描器"},
    "doctor.plugin_scanner": {"en": "Plugin Scanner", "zh": "插件扫描器"},
    "doctor.skills_declared": {
        "en": "Skills ({total} declared)",
        "zh": "技能 (声明 {total} 个)",
    },
    "doctor.skills_missing": {
        "en": "Skills ({total} declared, {missing} missing)",
        "zh": "技能 (声明 {total} 个，缺失 {missing} 个)",
    },
    "doctor.all_resolved": {"en": "all resolved", "zh": "全部解析成功"},
    "doctor.skills_none_detail": {
        "en": "no skills will be mounted for group '{group}'",
        "zh": "资源组 '{group}' 不会挂载任何技能",
    },
    # Deliberately not "run ca doctor --fix": seeding only applies to a
    # *missing* config.json, and this warning only fires when one exists.
    "doctor.skills_none_hint": {
        "en": (
            "Add entries to groups.{group}.skills in config.json "
            "(see config.example.json), or use the Web UI's Config Hub"
        ),
        "zh": (
            "请在 config.json 的 groups.{group}.skills 中添加技能 "
            "(可参考 config.example.json)，或通过 Web UI 的 Config Hub 配置"
        ),
    },
    "doctor.skills_hint": {
        "en": "Check skills/ directory or config.json groups",
        "zh": "请检查 skills/ 目录或 config.json 中的 groups",
    },
    "doctor.skills_error": {"en": "Skills resolution", "zh": "技能解析"},
    "doctor.hooks_resolved": {
        "en": "Hooks ({count} resolved)",
        "zh": "钩子 (解析 {count} 个)",
    },
    "doctor.hooks_unresolved": {
        "en": "Hooks ({declared} declared, {missing} unresolved)",
        "zh": "钩子 (声明 {declared} 个，未解析 {missing} 个)",
    },
    "doctor.hooks_hint": {
        "en": "Check hooks/ directory or metadata.json files",
        "zh": "请检查 hooks/ 目录或各 metadata.json 文件",
    },
    "doctor.hooks_error": {"en": "Hooks resolution", "zh": "钩子解析"},
    "doctor.plugins_resolved": {
        "en": "Plugins ({count} resolved)",
        "zh": "插件 (解析 {count} 个)",
    },
    "doctor.plugins_unresolved": {
        "en": "Plugins ({declared} declared, {missing} unresolved)",
        "zh": "插件 (声明 {declared} 个，未解析 {missing} 个)",
    },
    "doctor.plugins_hint": {
        "en": "Check plugins/ directory",
        "zh": "请检查 plugins/ 目录",
    },
    "doctor.plugins_error": {"en": "Plugins resolution", "zh": "插件解析"},
    "doctor.skipped": {"en": "Skipped", "zh": "已跳过"},
    "doctor.skipped_no_config": {
        "en": "config.json could not be loaded",
        "zh": "config.json 无法加载",
    },
    "doctor.could_not_evaluate": {
        "en": "could not evaluate: {error}",
        "zh": "无法检测: {error}",
    },
    # environment
    "doctor.temp_prompt_ok": {
        "en": "Temp prompt dir writable",
        "zh": "临时提示词目录可写",
    },
    "doctor.temp_prompt_label": {"en": "Temp prompt dir", "zh": "临时提示词目录"},
    "doctor.temp_prompt_failed": {
        "en": "not writable: {error}",
        "zh": "不可写: {error}",
    },
    "doctor.temp_prompt_hint": {
        "en": "Check permissions on {path}, or set TMPDIR/TEMP elsewhere",
        "zh": "请检查 {path} 的权限，或将 TMPDIR/TEMP 指向其他位置",
    },
    "doctor.proxy_label": {"en": "Proxy", "zh": "代理"},
    "doctor.proxy_unset": {
        "en": "not configured (use --proxy flag to enable)",
        "zh": "未配置 (使用 --proxy 参数启用)",
    },
    "doctor.proxy_reachable": {"en": "reachable", "zh": "可连通"},
    "doctor.proxy_unreachable": {
        "en": "none of the configured addresses reachable ({addresses})",
        "zh": "配置的地址均无法连通 ({addresses})",
    },
    "doctor.proxy_hint": {
        "en": "Start your proxy or update config.json",
        "zh": "请启动代理，或更新 config.json",
    },
    "doctor.symlink_label": {"en": "Symlink capability", "zh": "符号链接能力"},
    "doctor.symlink_unix": {
        "en": "Unix (symlinks available)",
        "zh": "Unix (支持符号链接)",
    },
    "doctor.junction_label": {
        "en": "Windows junction support",
        "zh": "Windows 目录联接支持",
    },
    "doctor.junction_ok": {
        "en": "available (no admin required)",
        "zh": "可用 (无需管理员权限)",
    },
    "doctor.junction_failed": {
        "en": "mklink /j failed — skill linking may not work ({detail})",
        "zh": "mklink /j 失败 —— 技能挂载可能无法工作 ({detail})",
    },
    "doctor.junction_exit_code": {
        "en": "mklink /j exited with code {code}",
        "zh": "mklink /j 退出码为 {code}",
    },
    "doctor.junction_hint": {
        "en": "Enable Developer Mode or run as Administrator",
        "zh": "请开启开发者模式，或以管理员身份运行",
    },
    # cross-engine parity
    "doctor.hook_delivery_label": {"en": "Hook delivery", "zh": "钩子生效情况"},
    "doctor.hook_delivery_none": {
        "en": "no hooks configured for this group",
        "zh": "当前资源组没有配置钩子",
    },
    "doctor.hook_delivery_count": {
        "en": "Hook delivery ({count})",
        "zh": "钩子生效情况 ({count})",
    },
    "doctor.hook_delivery_supported": {
        "en": "claude, gemini, opencode: supported",
        "zh": "claude, gemini, opencode: 支持",
    },
    "doctor.codex_hooks_label": {"en": "codex hooks", "zh": "codex 钩子"},
    "doctor.codex_trusted": {"en": "project is trusted", "zh": "项目已被信任"},
    "doctor.codex_untrusted": {
        "en": "'{project}' is not a trusted codex project; hooks are ignored",
        "zh": "'{project}' 不是受信任的 codex 项目，钩子会被忽略",
    },
    "doctor.codex_trust_hint": {
        "en": 'Add [projects."{project}"] with trust_level = "trusted" to {config}',
        "zh": '在 {config} 中加入 [projects."{project}"] 并设置 trust_level = "trusted"',
    },
    "doctor.codex_trust_unknown": {
        "en": "trust state unknown: {error}",
        "zh": "信任状态未知: {error}",
    },
    "doctor.mcp_drift_label": {"en": "MCP drift", "zh": "MCP 配置漂移"},
    "doctor.mcp_servers_label": {"en": "MCP servers", "zh": "MCP 服务"},
    "doctor.mcp_none": {
        "en": "none configured on any engine",
        "zh": "所有引擎均未配置",
    },
    "doctor.mcp_in_sync_label": {
        "en": "MCP servers ({count})",
        "zh": "MCP 服务 ({count} 个)",
    },
    "doctor.mcp_in_sync": {
        "en": "configured identically on all four engines",
        "zh": "四个引擎的配置完全一致",
    },
    "doctor.mcp_drift_count": {
        "en": "MCP drift ({count} server(s) not on every engine)",
        "zh": "MCP 配置漂移 ({count} 个服务未覆盖全部引擎)",
    },
    "doctor.mcp_drift_entry": {
        "en": "{name} (on: {engines})",
        "zh": "{name} (已配置: {engines})",
    },
    "doctor.mcp_drift_more": {"en": ", +{count} more", "zh": ", 另有 {count} 个"},
    "doctor.mcp_drift_hint": {
        "en": "Run: ca mcp sync <engine>   (add --dry-run to preview)",
        "zh": "运行: ca mcp sync <engine>   (加 --dry-run 可预览)",
    },
    # session integrity
    "doctor.stale_label": {"en": "Stale injections", "zh": "残留注入"},
    "doctor.stale_found": {
        "en": "settings still contain _ca_injected marker: {names}",
        "zh": "以下配置仍带有 _ca_injected 标记: {names}",
    },
    "doctor.stale_hint": {
        "en": "Run: ca doctor --fix  (auto-restores from .bak backups)",
        "zh": "运行: ca doctor --fix  (自动从 .bak 备份恢复)",
    },
    "doctor.stale_none": {"en": "none found", "zh": "未发现"},
    "doctor.dry_run_banner": {
        "en": "  --dry-run: no changes will be made. Preview of 'ca doctor --fix':",
        "zh": "  --dry-run: 不会做任何改动。以下是 'ca doctor --fix' 的预览:",
    },
    "doctor.applying_fixes": {"en": "  Applying fixes...", "zh": "  正在修复..."},
    "doctor.fixes_done": {
        "en": "  Done. Re-run 'ca doctor' to verify.",
        "zh": "  完成。请重新运行 'ca doctor' 确认。",
    },
    "doctor.restored": {
        "en": "  Restored {path} from backup",
        "zh": "  已从备份恢复 {path}",
    },
    "doctor.removed_injected": {
        "en": "  Removed injected {path}",
        "zh": "  已删除注入的 {path}",
    },
    "doctor.would_restore": {
        "en": "  Would restore {path} from backup",
        "zh": "  将从备份恢复 {path}",
    },
    "doctor.would_remove": {
        "en": "  Would remove injected {path}",
        "zh": "  将删除注入的 {path}",
    },
    # --- top level ---
    "cli.cancelled": {"en": "\n\nCancelled", "zh": "\n\n已取消"},
}


def t(key: str, **kwargs: Any) -> str:
    """Returns the message for ``key`` in the active language.

    Falls back to English, then to the key itself, so a missing translation
    degrades to something readable rather than raising mid-command.
    """
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    template = entry.get(resolve_language()) or entry.get(DEFAULT_LANGUAGE) or key
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template
