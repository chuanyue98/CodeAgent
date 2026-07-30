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
