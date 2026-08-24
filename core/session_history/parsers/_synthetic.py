"""Recognizing CLI bookkeeping that masquerades as a user turn.

Claude Code and CodeBuddy Code (which shares its transcript format) both record
some of their own events as ordinary ``role: "user"`` rows whose content is a
synthetic XML-ish blob rather than anything the person typed: slash commands,
their echoed output, ``!``-prefixed shell input, injected system reminders, and
background task notifications.

Nothing on the row marks them as such -- ``isMeta`` is set on a different class
of row entirely -- so the opening tag is the only signal available.

They have to be dropped when building a :class:`UnifiedSession` because that
session is what gets written into *another* engine. They are frequently the
first user row in a file, and
:attr:`~core.session_history.models.UnifiedSession.first_user_message` feeds the
converted session's title, so sessions converted out of Claude Code were landing
in OpenCode named ``<command-name>/clear</command-name>`` with a ``/clear``
replayed at the top of the transcript.
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
