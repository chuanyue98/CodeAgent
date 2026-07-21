from __future__ import annotations

import os
import sys
import time
from typing import BinaryIO
from pathlib import Path


class LockManager:
    """Manages inter-process file locking for engine resources."""

    def acquire_resource_lock(self, lock_path: Path) -> BinaryIO:
        """Acquire an inter-process lock for mutable engine resources.

        Blocks until the lock is free, matching ``flock(LOCK_EX)``'s
        semantics on POSIX. ``msvcrt.locking()`` only retries for ~10s
        before raising, so on Windows this polls in a loop instead to get
        the same block-until-free behavior rather than failing out from
        under a second concurrent process that's still holding the lock.
        """
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                # Generous enough to outlast a real interactive session
                # holding the lock, but bounded so a permanently stuck or
                # OS-refused lock still surfaces as an error instead of
                # hanging forever.
                max_attempts = 7200  # ~30 minutes at 0.25s per attempt
                for attempt in range(max_attempts):
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if attempt == max_attempts - 1:
                            raise
                        time.sleep(0.25)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except BaseException:
            handle.close()
            raise
        return handle

    def release_resource_lock(self, handle: BinaryIO) -> None:
        """Release a handle returned by :meth:`acquire_resource_lock`."""
        try:
            handle.seek(0)
            if sys.platform == "win32":
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
