import os
from pathlib import Path

import pytest

from core import i18n
from core.web.security import reset_token_cache


@pytest.fixture(autouse=True)
def isolated_session_index(tmp_path, monkeypatch):
    """把会话索引指到 tmp，并在每个用例后丢掉进程级单例。

    索引单例是 ``~/.codeagent/session-index.sqlite3``，一旦被某个用例意外创建
    就会：一是读写开发者真实的库，二是被后续用例复用（引擎 HOME 已被别的
    fixture 改掉），于是断言莫名失败。这里默认重定向 + 每例重置。
    """
    monkeypatch.setenv(
        "CA_SESSION_INDEX_DB", str(tmp_path / "session-index.sqlite3")
    )
    yield
    from core.session_history.index_ingest import reset_indexer_for_tests
    from core.session_history.index_store import reset_index_for_tests

    reset_indexer_for_tests()
    reset_index_for_tests()


@pytest.fixture
def no_session_index(monkeypatch):
    """关掉会话索引，让读路径确定地走回退实现。

    凡是要给 ``repository.find_all_sessions`` / ``find_session_by_id`` 打桩的
    用例都需要它：否则后台同步可能抢先把索引建好，读路径就不走回退了，测试会
    随机失败。
    """
    monkeypatch.setenv("CA_SESSION_INDEX", "0")


@pytest.fixture(autouse=True)
def pinned_language(monkeypatch):
    """Pins CLI output to English for the whole suite.

    Many tests assert on user-facing CLI strings. Language resolution reads
    ``language`` from the developer's real config.json (see core/i18n.py), so
    switching the Web UI to Chinese -- which writes that same field -- turned
    a dozen unrelated tests red. CA_LANG is the highest-precedence source, so
    setting it here makes those assertions independent of local config.
    """
    monkeypatch.setenv(i18n.ENV_VAR, "en")
    monkeypatch.setattr(i18n, "_resolved", None, raising=False)
    yield
    monkeypatch.setattr(i18n, "_resolved", None, raising=False)


@pytest.fixture(autouse=True)
def web_security_test_env(monkeypatch):
    """Relaxes the Web UI's local-origin gates for unit tests.

    Two adjustments, for different reasons:

    ``CA_UI_ALLOWED_HOSTS=*``
        Test clients send a synthetic Host (``testserver``, ``test``, and
        others depending on each file's ``base_url``), which the rebinding
        defence in :class:`~core.web.security.HostHeaderMiddleware`
        correctly rejects. That is a test-harness artifact, not a behaviour
        worth asserting in every router test.
    ``CA_UI_AUTH=off``
        Router tests build their own bare FastAPI app (no router-level
        ``Depends``), so the token gate only reaches them through the two
        WebSocket routes that check it inline. Disabling it keeps those
        tests about the transport they actually cover.

    The gates themselves are verified directly in ``test_web_security.py``,
    which re-enables both, and end-to-end by the Playwright suite, which
    runs against a server with auth fully on (see e2e/start-server.sh).
    """
    monkeypatch.setenv("CA_UI_ALLOWED_HOSTS", "*")
    monkeypatch.setenv("CA_UI_AUTH", "off")
    reset_token_cache()
    yield
    reset_token_cache()


@pytest.fixture(autouse=True)
def isolated_runner_state():
    """Clears the shared web runner singleton before each test.

    core.web.routers.tasks builds a module-level ``TaskRunner(ROOT_DIR)``
    whose constructor reloads any still-"running" rows from the repo's
    ``.ca_task_logs/runs.db``. A stale row left by a crashed or manual
    session leaks into every test that aggregates runner state -- e.g.
    test_instances_router's "empty without gateway" assertion goes red.
    Only in-memory state is cleared; the SQLite store is left untouched so
    tests exercising run history keep working.
    """
    from core.web.routers import tasks as tasks_router

    runner = tasks_router._runner
    with runner._run_lock:
        runner.active_runs.clear()
        runner._processes.clear()
        runner._stopping_tasks.clear()
    yield
    with runner._run_lock:
        runner.active_runs.clear()
        runner._processes.clear()
        runner._stopping_tasks.clear()


@pytest.fixture
def fake_bin(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bin_dir


@pytest.fixture
def home(tmp_path, monkeypatch):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    return home_dir
