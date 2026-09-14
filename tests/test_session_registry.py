from __future__ import annotations

from core.lock_manager import LockManager, SessionRegistry


def _registry(tmp_path, scope="project"):
    return SessionRegistry(tmp_path / scope, state_root=tmp_path / "state")


def test_try_acquire_reports_a_lock_held_by_another_handle(tmp_path):
    manager = LockManager()
    path = tmp_path / "resource.lock"

    held = manager.try_acquire_resource_lock(path)
    assert held is not None
    try:
        assert manager.try_acquire_resource_lock(path) is None
    finally:
        manager.release_resource_lock(held)

    again = manager.try_acquire_resource_lock(path)
    assert again is not None
    manager.release_resource_lock(again)


def test_lone_session_is_the_last_one_to_leave(tmp_path):
    registry = _registry(tmp_path)
    with registry.exclusive():
        registry.join()

    with registry.exclusive():
        assert registry.leave() is True
    assert not list(registry.directory.glob("*.session"))


def test_second_session_joins_without_waiting_for_the_first(tmp_path):
    first = _registry(tmp_path)
    second = _registry(tmp_path)
    with first.exclusive():
        first.join()

    # 旧实现在整个会话期间持有排他锁，这里会一直卡住。
    with second.exclusive():
        second.join()

    with first.exclusive():
        assert first.leave() is False
    with second.exclusive():
        assert second.leave() is True


def test_session_file_left_by_a_dead_process_is_pruned(tmp_path):
    registry = _registry(tmp_path)
    registry.directory.mkdir(parents=True)
    stale = registry.directory / "12345-deadbeef.session"
    stale.write_bytes(b"\0")

    with registry.exclusive():
        assert registry.leave() is True
    assert not stale.exists()


def test_different_scopes_do_not_see_each_other(tmp_path):
    a = _registry(tmp_path, "a")
    b = _registry(tmp_path, "b")
    with a.exclusive():
        a.join()

    with b.exclusive():
        assert b.leave() is True
    with a.exclusive():
        assert a.leave() is True
