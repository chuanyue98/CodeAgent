import os
import tempfile
from pathlib import Path

import pytest

# 必须在导入任何 CLI 模块之前落定：Click 的 help 文案是在装饰器求值时
# 定下来的，等 pinned_language fixture 跑起来已经晚了。
os.environ.setdefault("CA_LANG", "en")

# 服务 lifespan 启停都会 kill-server 浏览器终端的 tmux server。默认 socket
# 是开发者正在用的 `ca ui`：不隔离的话，跑一次测试就把他开着的终端全杀了。
# 直接覆盖而不是 setdefault：环境里若指着真实 socket，照样得换掉。
_PYTEST_TMUX_SOCKET = f"ca-pytest-{os.getpid()}"
os.environ["CA_PTY_TMUX_SOCKET"] = _PYTEST_TMUX_SOCKET

# 会话索引从 ~/.claude、~/.codex 等目录读数据源。不换 HOME 的话，每个用例的
# 空索引都会把开发者本机的全部会话解析一遍：结果随机器而变，且很慢。
_PYTEST_HOME = tempfile.mkdtemp(prefix="ca-pytest-home-")
os.environ["HOME"] = _PYTEST_HOME
os.environ["USERPROFILE"] = _PYTEST_HOME
os.environ["CA_DATA_DIR"] = str(Path(_PYTEST_HOME) / "data")

# 各引擎 CLI 在回落到 HOME 下的目录之前，会先读自己的变量。开发者的 shell 里
# 留着的，或者测试本身跑在一次委派里继承来的（委派的 codex 拿到的是隔离
# home），都会让用例读写真实的引擎配置。换了 HOME 还不够，这些一并清掉。
# 新增一个 ca 会读的引擎目录变量时，记得加进来。
ENGINE_HOME_VARS = (
    "CODEX_HOME",
    "CA_USER_CODEX_HOME",
    "CA_ISOLATED_HOME",
    "CLAUDE_CONFIG_DIR",
    "CODEBUDDY_CONFIG_DIR",
    "OPENCODE_CONFIG_DIR",
    "OPENCODE_CONFIG",
)
for _var in ENGINE_HOME_VARS:
    os.environ.pop(_var, None)

from core import i18n  # noqa: E402
from core.web.security import reset_token_cache  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _reap_pytest_tmux_server():
    """测试结束时收掉本次测试专用的 tmux server 和临时 HOME。"""
    yield
    import shutil
    import subprocess

    shutil.rmtree(_PYTEST_HOME, ignore_errors=True)
    if shutil.which("tmux"):
        subprocess.run(
            ["tmux", "-L", _PYTEST_TMUX_SOCKET, "kill-server"],
            capture_output=True,
            timeout=10,
            check=False,
        )


@pytest.fixture(autouse=True)
def isolated_session_index(tmp_path, monkeypatch):
    """把会话索引指到 tmp，并在每个用例后丢掉进程级单例。

    索引单例是 ``~/.codeagent/session-index.sqlite3``，一旦被某个用例意外创建
    就会：一是读写开发者真实的库，二是被后续用例复用（引擎 HOME 已被别的
    fixture 改掉），于是断言莫名失败。这里默认重定向 + 每例重置。
    """
    monkeypatch.setenv("CA_SESSION_INDEX_DB", str(tmp_path / "session-index.sqlite3"))
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


@pytest.fixture
def fast_process_teardown(monkeypatch):
    """把各 adapter 收尾子进程时的两段等待缩到 50ms。

    用例要验的是「SIGKILL 也收不掉时会放弃」，不必真等满 8~10 秒。
    """
    from core.services.agent_adapters import (
        _process_lifecycle,
        codebuddy,
        codex,
        opencode,
    )

    real = _process_lifecycle.graceful_terminate

    async def fast(process, **kwargs):
        kwargs.update(terminate_timeout=0.05, kill_timeout=0.05)
        await real(process, **kwargs)

    for module in (codebuddy, codex, opencode):
        monkeypatch.setattr(module, "graceful_terminate", fast)


@pytest.fixture(autouse=True)
def pinned_language(monkeypatch):
    """Pins CLI output to English for the whole suite.

    Many tests assert on user-facing CLI strings. Language resolution reads
    ``language`` from the developer's real config.json (see core/i18n.py), so
    switching the Web UI to Chinese -- which writes that same field -- turned
    a dozen unrelated tests red. CA_LANG is the highest-precedence source, so
    setting it here makes those assertions independent of local config.

    模块顶部还会先设一次同样的值——那一次管住导入期求值的 Click help，这里
    这一次管住用例运行期，并负责重置缓存。
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
def isolated_runner_state(tmp_path_factory, monkeypatch):
    """按用例隔离 web runner 运行数据目录，并保持延迟初始化不被空转触发。

    ``core.web.routers.tasks`` 使用 ``LazyTaskRunner`` 延迟打开 ``runs.db``。
    若无条件读取 ``_runner._run_lock``，会在每个测试前强制建库，既慢又掩盖
    导入副作用检查；同时使用 ``tmp_path_factory`` 独立目录避免污染测试自身的
    ``tmp_path``（许多测试会断言 ``tmp_path`` 为空或仅含 git 仓库文件）。
    """
    from core.web.routers import tasks as tasks_router

    tasks_router._runner.close()
    runtime_dir = tmp_path_factory.mktemp("ca-runtime")
    monkeypatch.setenv("CA_DATA_DIR", str(runtime_dir))
    yield
    if getattr(tasks_router._runner, "is_initialized", False):
        tasks_router._runner.kill_all()
        tasks_router._runner.close()


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


@pytest.fixture(autouse=True)
def not_quiet(monkeypatch):
    """测试本身可能跑在一次委派里，继承来的 CA_QUIET 会改掉日志级别和启动横幅。"""
    from core.logging_config import QUIET_ENV

    monkeypatch.delenv(QUIET_ENV, raising=False)


@pytest.fixture(autouse=True)
def no_codeagent_mcp_mount(monkeypatch):
    """默认不给引擎挂 codeagent MCP：不少用例逐字断言启动命令。

    测挂载本身的用例 ``monkeypatch.delenv(DEPTH_ENV)`` 把它打开。
    """
    from core.delegation_depth import DEPTH_ENV, MAX_DELEGATION_DEPTH

    monkeypatch.setenv(DEPTH_ENV, str(MAX_DELEGATION_DEPTH))
