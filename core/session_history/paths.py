"""Canonical form for the project paths recorded in session history.

Every engine writes the working directory into its own history in its own
spelling, and the same directory legitimately shows up several ways:

    E:/demo/CodeAgent            (opencode)
    E:\\demo\\CodeAgent            (claude)
    \\\\?\\E:\\demo\\CodeAgent         (codex, Windows extended-length form)
    \\\\?\\UNC\\server\\share\\proj    (codex, UNC under the same form)

Comparing those as plain strings splits one workspace into several, which is
how filtering Sessions by a workspace ended up hiding the codex runs for that
very directory. One helper, used by every parser and by the analytics router,
so the whole app agrees on what "the same project" means.
"""

from __future__ import annotations

import re

# Windows extended-length prefixes. `\\?\UNC\server\share` denotes the network
# path `\\server\share`, so that one is rewritten rather than merely dropped.
_EXTENDED_UNC_PREFIX = "//?/unc/"
_EXTENDED_PREFIX = "//?/"


def strip_extended_length_prefix(path: str) -> str:
    """Removes a Windows extended-length prefix, leaving case untouched.

    For callers that compare paths but also display or store the result, so
    folding case would leak into the UI. Expects forward slashes already.
    """
    lowered = path.lower()
    if lowered.startswith(_EXTENDED_UNC_PREFIX):
        return "//" + path[len(_EXTENDED_UNC_PREFIX) :]
    if lowered.startswith(_EXTENDED_PREFIX):
        return path[len(_EXTENDED_PREFIX) :]
    return path


def normalize_project_path(path: str) -> str:
    """Canonicalizes a project path for equality comparison.

    Separators unified, case folded, trailing separator dropped, and Windows
    extended-length prefixes resolved — so a workspace registered as
    ``E:\\demo\\App`` matches session records written as ``e:/demo/app/`` or
    ``\\\\?\\E:\\demo\\App``.

    Comparison only: the result is not a path to hand back to the filesystem or
    show to anyone. Use :func:`strip_extended_length_prefix` when the value is
    also displayed or stored.
    """
    return strip_extended_length_prefix(path.replace("\\", "/").lower()).rstrip("/")


def decode_claude_project_path(dir_name: str) -> str:
    """Decodes Claude's dash-encoded directory name back to a file path.

    Claude encodes paths as: ``E:\\demo\\CodeAgent`` → ``E--demo-CodeAgent``.
    Note: single dashes in directory names (e.g. ``hearthstone-bot``) are
    ambiguous — they could be a path separator or part of the name.
    This function returns a best-guess decode; use ``claude_dir_matches``
    for reliable project path matching.
    """
    m = re.match(r"^([A-Za-z])--(.*)$", dir_name)
    if m:
        drive, rest = m.groups()
        return f"{drive}:/{rest.replace('-', '/')}"
    return dir_name.replace("-", "/")


def encode_claude_project_dir(path: str) -> str:
    """Encodes a path the way Claude Code names ``~/.claude/projects/<dir>``.

    Every character that is not an ASCII letter or digit becomes a single
    ``-``: ``E:\\demo\\hearthstone-bot`` -> ``E--demo-hearthstone-bot``.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def claude_dir_matches(dir_name: str, target_path: str) -> bool:
    """Checks if a Claude project directory name matches a target file path."""
    normalized_target = strip_extended_length_prefix(
        target_path.replace("\\", "/")
    ).rstrip("/")
    if not normalized_target:
        return False
    return dir_name.lower() == encode_claude_project_dir(normalized_target).lower()


def encode_codebuddy_project_dir(path: str) -> str:
    """Encodes a file path the way CodeBuddy Code names its
    ``~/.codebuddy/projects/<dir>`` directory.
    """
    p = path.replace("\\", "/")
    if re.match(r"^[A-Za-z]:", p):
        p = p[0].lower() + p[1:]
    return re.sub(r"[^A-Za-z0-9]+", "-", p).lstrip("-")


def codebuddy_dir_matches(dir_name: str, target_path: str) -> bool:
    """Checks if a CodeBuddy projects directory name matches a target path."""
    normalized_target = strip_extended_length_prefix(
        target_path.replace("\\", "/")
    ).rstrip("/")
    if not normalized_target:
        return False
    return dir_name.lower() == encode_codebuddy_project_dir(normalized_target).lower()


# Backward compatibility aliases
_decode_claude_project_path = decode_claude_project_path
_encode_claude_project_dir = encode_claude_project_dir
_claude_dir_matches = claude_dir_matches
_encode_codebuddy_project_dir = encode_codebuddy_project_dir
_codebuddy_dir_matches = codebuddy_dir_matches
