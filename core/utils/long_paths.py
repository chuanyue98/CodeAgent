"""Windows MAX_PATH escape hatch, for both halves of session history.

Claude Code and CodeBuddy Code name a session directory after the *whole*
project path with the separators replaced, so a project a few levels down
becomes one ~200-character directory component::

    E:/demo/CodeAgent          ->  E--demo-CodeAgent
    E:/work/team/svc/api/v2/…  ->  E--work-team-svc-api-v2-…

Past 260 characters the ordinary Windows API refuses the path, and both
writing such a file and reading it back fail with ``FileNotFoundError
[WinError 3]`` naming a path that plainly exists. Prefixing with ``\\\\?\\``
opts a single call out of the limit without moving anything: the file lands
where the other tools look for it, which is the entire point of writing it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Longest path the ordinary Windows API accepts.
WINDOWS_MAX_PATH = 260

EXTENDED_PREFIX = "\\\\?\\"


def long_path(path: Path | str) -> str:
    """Returns *path* in a spelling that survives Windows' MAX_PATH limit.

    A no-op off Windows, on already-prefixed paths, and on paths short
    enough not to need it -- so callers can route every filesystem access
    through it without changing behaviour in the common case.

    The prefix requires a resolved absolute path with back-slashes and no
    ``.``/``..`` segments; anything that cannot be resolved comes back
    unchanged rather than becoming a path that names nothing.
    """
    text = str(path)
    if sys.platform != "win32":
        return text
    if text.startswith(EXTENDED_PREFIX) or len(text) < WINDOWS_MAX_PATH:
        return text
    try:
        resolved = str(Path(text).resolve())
    except (OSError, ValueError):
        return text
    if resolved.startswith(EXTENDED_PREFIX):
        return resolved
    if resolved.startswith("\\\\"):  # UNC: \\server\share -> \\?\UNC\server\share
        return EXTENDED_PREFIX + "UNC" + resolved[1:]
    return EXTENDED_PREFIX + resolved


def list_dirs(base: Path) -> list[Path]:
    """Subdirectories of *base*, visible past MAX_PATH.

    ``Path.iterdir`` and ``Path.glob`` cannot see into a long directory even
    when handed the prefixed spelling -- pathlib re-normalizes the pattern
    and the prefix is lost -- but ``os.scandir`` accepts it. Without this a
    deep project's sessions land on disk correctly and never appear in any
    listing, which is a worse failure than refusing to write them.

    Returns plain (unprefixed) paths so callers can store and display them;
    anything that touches the filesystem with one should pass it through
    :func:`long_path` first.
    """
    try:
        with os.scandir(long_path(base)) as entries:
            return [base / entry.name for entry in entries if entry.is_dir()]
    except OSError:
        return []


def list_files(base: Path, suffix: str, *, recursive: bool = False) -> list[Path]:
    """Files under *base* whose name ends with *suffix*, visible past MAX_PATH.

    See :func:`list_dirs` for why ``glob``/``rglob`` are not used.
    """
    found: list[Path] = []
    try:
        with os.scandir(long_path(base)) as entries:
            for entry in entries:
                child = base / entry.name
                if entry.is_dir():
                    if recursive:
                        found.extend(list_files(child, suffix, recursive=True))
                elif entry.name.endswith(suffix):
                    found.append(child)
    except OSError:
        return found
    return found


def exists(path: Path) -> bool:
    """``Path.exists`` that also works past MAX_PATH.

    The plain method reports False for a file that is merely too deep to
    name, so an existence guard written with it rejects exactly the files
    this module exists to reach.
    """
    return os.path.exists(long_path(path))


def mtime(path: Path) -> float:
    """``st_mtime`` for *path*, readable past MAX_PATH. 0.0 when unreadable."""
    try:
        return os.stat(long_path(path)).st_mtime
    except OSError:
        return 0.0
