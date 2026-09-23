from __future__ import annotations

import hashlib
import os
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

# Generous enough to outlast a real interactive session holding the lock,
# but bounded so a permanently stuck or OS-refused lock still surfaces as an
# error instead of hanging forever. ~5 minutes at 0.25s per attempt.
_WINDOWS_LOCK_MAX_ATTEMPTS = 1200


def _open_lock_file(lock_path: Path) -> BinaryIO:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
    except BaseException:
        handle.close()
        raise
    return handle


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
        handle = _open_lock_file(lock_path)
        try:
            if sys.platform == "win32":
                import msvcrt

                max_attempts = _WINDOWS_LOCK_MAX_ATTEMPTS
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

    def try_acquire_resource_lock(self, lock_path: Path) -> BinaryIO | None:
        """不等待地试锁；锁被其他句柄持有时返回 ``None``。"""
        handle = _open_lock_file(lock_path)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return None
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


def default_session_state_root() -> Path:
    return Path.home() / ".codeagent" / "sessions"


class SessionRegistry:
    """同一注入范围内并发 ca 会话的登记表。

    注入（技能链接、settings 里的钩子等）在会话开始时做，最后一个会话退出时
    才还原。只有「做注入」和「判断要不要还原」这两步互斥，会话运行期间不持
    公共锁，所以同一项目可以同时开多个会话。

    每个会话锁住自己的登记文件，进程一退出（包括被强杀）锁就由操作系统释放，
    所以「还有没有别的会话」靠试锁判断，而不是看 pid 是否存在。
    """

    def __init__(
        self,
        scope: Path,
        state_root: Path | None = None,
        lock_manager: LockManager | None = None,
    ):
        digest = hashlib.sha256(str(scope.resolve()).encode("utf-8")).hexdigest()
        root = state_root if state_root is not None else default_session_state_root()
        self.directory = root / digest[:16]
        self._locks = lock_manager or LockManager()
        self._own: tuple[Path, BinaryIO] | None = None

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        handle = self._locks.acquire_resource_lock(self.directory / "setup.lock")
        try:
            yield
        finally:
            self._locks.release_resource_lock(handle)

    def join(self) -> None:
        """登记当前会话。调用方须持有 :meth:`exclusive`。"""
        path = self.directory / f"{os.getpid()}-{uuid.uuid4().hex[:8]}.session"
        handle = self._locks.try_acquire_resource_lock(path)
        if handle is None:
            raise OSError(f"Cannot lock session file: {path}")
        self._own = (path, handle)

    def note_scope_created(self) -> None:
        """记下注入范围目录是这批会话建出来的。调用方须持有 :meth:`exclusive`。"""
        (self.directory / "scope-created").touch()

    def take_scope_created(self) -> bool:
        """取出并清掉 :meth:`note_scope_created` 的记录。调用方须持有 :meth:`exclusive`。"""
        marker = self.directory / "scope-created"
        if not marker.exists():
            return False
        marker.unlink(missing_ok=True)
        return True

    def leave(self) -> bool:
        """注销当前会话，返回是否已经没有其他存活会话。调用方须持有 :meth:`exclusive`。"""
        if self._own is not None:
            path, handle = self._own
            self._own = None
            self._locks.release_resource_lock(handle)
            path.unlink(missing_ok=True)

        alone = True
        for path in self.directory.glob("*.session"):
            probe = self._locks.try_acquire_resource_lock(path)
            if probe is None:
                alone = False
                continue
            # 能锁上说明持有者已经不在了，是没来得及注销的残留。
            self._locks.release_resource_lock(probe)
            path.unlink(missing_ok=True)
        return alone
