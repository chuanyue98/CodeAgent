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

from core.i18n.messages.cli import CLI_MESSAGES
from core.i18n.messages.doctor import DOCTOR_MESSAGES
from core.i18n.messages.mcp import MCP_MESSAGES

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
    **CLI_MESSAGES,
    **DOCTOR_MESSAGES,
    **MCP_MESSAGES,
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
