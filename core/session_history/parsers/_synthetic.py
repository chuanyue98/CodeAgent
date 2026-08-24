"""Recognizing CLI bookkeeping that masquerades as a user turn.

Claude Code and CodeBuddy Code (which shares its transcript format) record some
of their own events as ordinary ``role: "user"`` rows whose content is a
synthetic XML-ish blob: slash commands, their echoed output, ``!``-prefixed
shell input, injected system reminders, task notifications. Nothing on the row
marks them as such, so the opening tag is the only signal.

They are dropped when building a :class:`UnifiedSession` because that session
gets written into another engine, where they would replay as real turns and
supply the converted session's title.
"""

from __future__ import annotations

_SYNTHETIC_USER_PREFIXES = (
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<local-command-caveat>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<task-notification>",
    "<system-reminder",  # no ``>``: real rows carry attributes on this one
)


def is_synthetic_user_content(text: str) -> bool:
    """Reports whether *text* is a CLI-generated row rather than a real turn.

    Args:
        text: The extracted user message text.

    Returns:
        bool: True when the message is the CLI's own bookkeeping.
    """
    return text.lstrip().startswith(_SYNTHETIC_USER_PREFIXES)
