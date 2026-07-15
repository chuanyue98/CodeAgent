from __future__ import annotations

import os
from typing import BinaryIO
from pathlib import Path


class LockManager:
    """Manages inter-process file locking for engine resources."""

    def acquire_resource_lock(self, lock_path: Path) -> BinaryIO:
        """Acquire an inter-process lock for mutable engine resources."""
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(
                handle.fileno(),
                msvcrt.LK_LOCK,
                1,
            )
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    def release_resource_lock(self, handle: BinaryIO) -> None:
        """Release a handle returned by :meth:`acquire_resource_lock`."""
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(
                    handle.fileno(),
                    msvcrt.LK_UNLCK,
                    1,
                )
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
