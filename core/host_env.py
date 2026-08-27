"""Keeps the agent that launched CodeAgent out of the agent CodeAgent launches.

CodeAgent's job is to spawn other vendors' agent CLIs, and it is perfectly
normal for it to be *run from inside one of them* -- ``ca claude`` typed into
a Claude Code session, a task fired from a terminal that session opened.
Copying ``os.environ`` wholesale then hands the child a set of variables that
describe the parent session, which is wrong in three separate ways:

* Identity. ``CLAUDE_CODE_SESSION_ID`` names the *host's* conversation. A
  launched engine reading it is being told it is a session it is not.
* Isolation. ``CLAUDE_CODE_MESSAGING_SOCKET`` / ``_TOKEN`` are the host
  session's control channel and the credential for it. An engine CodeAgent
  spawns has no business holding either.
* Behaviour. ``CLAUDECODE`` and ``CLAUDE_CODE_CHILD_SESSION`` are how a CLI
  decides it is nested rather than top-level, which changes what it does --
  including whether it writes a transcript at all. CodeAgent's own session
  history is built on those transcripts.

The list is explicit rather than a ``CLAUDE_CODE_*`` prefix sweep: variables
in that namespace are also how a user deliberately configures the CLI (the
persistence override, for one), and silently eating those would trade one
surprising behaviour for another.
"""

from __future__ import annotations

import os

#: Variables that describe the *host* agent session rather than the user's
#: configuration. Credentials (API keys) and user config (``CLAUDE_CONFIG_DIR``)
#: are deliberately absent -- those belong to the user and must pass through,
#: or the launched engine cannot authenticate.
HOST_SESSION_MARKERS = frozenset(
    {
        # Nested-session flags.
        "CLAUDECODE",
        "CLAUDE_CODE_CHILD_SESSION",
        # Host session identity.
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_PID",
        # Host control channel + its credential.
        "CLAUDE_CODE_MESSAGING_SOCKET",
        "CLAUDE_CODE_MESSAGING_TOKEN",
        # How the host was invoked, and with what settings.
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_EXECPATH",
        "CLAUDE_EFFORT",
    }
)


def strip_host_markers(env: dict[str, str]) -> dict[str, str]:
    """Returns *env* without the launching agent's session markers.

    Args:
        env: An environment mapping, typically built from ``os.environ``.

    Returns:
        dict[str, str]: A new mapping; *env* is not modified.
    """
    return {key: value for key, value in env.items() if key not in HOST_SESSION_MARKERS}


def child_environ() -> dict[str, str]:
    """``os.environ`` as a launched engine should see it."""
    return strip_host_markers(dict(os.environ))
