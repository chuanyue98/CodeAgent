"""Atomic file write utility.

Writes content to a temporary file in the same directory, then atomically
replaces the target file using ``os.replace()``. This prevents file
corruption if the process crashes during a write.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path | str, content: str, encoding: str = "utf-8") -> None:
    """Writes *content* to *path* atomically.

    Creates parent directories if needed, writes to a temporary file in the
    same directory, then ``os.replace`` renames it to the final path. If any
    error occurs, the temporary file is cleaned up and the original file is
    left untouched.

    Args:
        path: Destination file path.
        content: Text content to write.
        encoding: Text encoding (default ``"utf-8"``).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
