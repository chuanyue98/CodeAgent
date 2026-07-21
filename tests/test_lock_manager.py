from __future__ import annotations

import sys
import types

import pytest

from core.lock_manager import LockManager


def test_acquire_and_release_lock_roundtrip(tmp_path):
    manager = LockManager()
    lock_path = tmp_path / "resource.lock"

    handle = manager.acquire_resource_lock(lock_path)
    try:
        assert lock_path.exists()
        assert not handle.closed
    finally:
        manager.release_resource_lock(handle)

    assert handle.closed


def test_acquire_resource_lock_closes_handle_on_locking_failure(tmp_path, monkeypatch):
    """If the platform locking call itself raises (contention, a stale
    lock the OS refuses, etc.), the opened file handle must not leak."""
    manager = LockManager()
    lock_path = tmp_path / "resource.lock"
    opened_handles = []
    original_open = open

    def tracking_open(*args, **kwargs):
        handle = original_open(*args, **kwargs)
        opened_handles.append(handle)
        return handle

    monkeypatch.setattr("builtins.open", tracking_open)

    if sys.platform == "win32":
        import msvcrt

        def raise_locking(*_args, **_kwargs):
            raise OSError("simulated lock failure")

        monkeypatch.setattr(msvcrt, "locking", raise_locking)
        # Permanent failure means every one of the ~30-minute retry budget's
        # attempts fails -- skip the real sleeps between them.
        monkeypatch.setattr("core.lock_manager.time.sleep", lambda _seconds: None)
    else:
        import fcntl

        def raise_flock(*_args, **_kwargs):
            raise OSError("simulated lock failure")

        monkeypatch.setattr(fcntl, "flock", raise_flock)

    with pytest.raises(OSError, match="simulated lock failure"):
        manager.acquire_resource_lock(lock_path)

    assert len(opened_handles) == 1
    assert opened_handles[0].closed


def test_acquire_resource_lock_retries_on_windows_instead_of_giving_up(
    tmp_path, monkeypatch
):
    """msvcrt.locking() only retries internally for ~10s before raising,
    which doesn't match flock(LOCK_EX)'s block-until-free semantics on
    POSIX -- acquire_resource_lock must keep retrying itself rather than
    propagate the first failure while another process still holds the lock."""
    manager = LockManager()
    lock_path = tmp_path / "resource.lock"

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("core.lock_manager.time.sleep", lambda _seconds: None)

    calls = {"count": 0}

    def flaky_locking(_fd, _mode, _size):
        calls["count"] += 1
        if calls["count"] < 3:
            raise OSError("lock still held")

    fake_msvcrt = types.SimpleNamespace(
        LK_NBLCK=1, LK_LOCK=1, LK_UNLCK=0, locking=flaky_locking
    )
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

    handle = manager.acquire_resource_lock(lock_path)
    try:
        assert calls["count"] == 3
    finally:
        handle.close()
