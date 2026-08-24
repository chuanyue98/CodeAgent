"""Writers for converting UnifiedSession to engine-native formats.

Each writer takes a UnifiedSession and writes it to the target engine's
session storage directory in that engine's native format.
"""

from core.session_history.writers.claude_writer import write_claude_session
from core.session_history.writers.codebuddy_writer import write_codebuddy_session
from core.session_history.writers.codex_writer import write_codex_session
from core.session_history.writers.gemini_writer import write_gemini_session
from core.session_history.writers.opencode_writer import write_opencode_session

__all__ = [
    "write_claude_session",
    "write_codebuddy_session",
    "write_codex_session",
    "write_gemini_session",
    "write_opencode_session",
    "write_session",
]


def write_session(session, target_engine: str) -> str:
    """Dispatches to the appropriate writer based on target engine.

    Args:
        session: A UnifiedSession to convert and write.
        target_engine: The target engine name ("claude", "codex", "gemini", "opencode", "codebuddy").

    Returns:
        str: The new session ID in the target engine's format.

    Raises:
        ValueError: If the target engine is not supported.
    """
    writers = {
        "claude": write_claude_session,
        "codex": write_codex_session,
        "gemini": write_gemini_session,
        "opencode": write_opencode_session,
        "codebuddy": write_codebuddy_session,
    }

    writer = writers.get(target_engine)
    if not writer:
        raise ValueError(f"Unsupported target engine: {target_engine}")

    return writer(session)
