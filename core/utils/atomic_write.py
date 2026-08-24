"""Atomic file write utility.

Writes content to a temporary file in the same directory, then atomically
replaces the target file using ``os.replace()``. This prevents file
corruption if the process crashes during a write.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from core.utils.long_paths import long_path


def atomic_write(path: Path | str, content: str, encoding: str = "utf-8") -> None:
    """Writes *content* to *path* atomically.

    Creates parent directories if needed, writes to a temporary file in the
    same directory, then ``os.replace`` renames it to the final path. If any
    error occurs, the temporary file is cleaned up and the original file is
    left untouched.

    Long Windows paths are handled rather than failing: the session writers
    name a directory after the whole project path, so a deep enough project
    used to make conversion die with a bare ``FileNotFoundError [WinError 3]``
    naming a path that plainly existed. See :mod:`core.utils.long_paths`.

    Args:
        path: Destination file path.
        content: Text content to write.
        encoding: Text encoding (default ``"utf-8"``).
    """
    path = Path(path)
    parent_target = long_path(path.parent)
    os.makedirs(parent_target, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=parent_target, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(tmp_path, long_path(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
