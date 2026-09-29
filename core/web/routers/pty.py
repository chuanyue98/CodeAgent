"""Browser-based PTY sessions -- the only terminal this server opens.

Attaches an engine CLI to a pseudo-terminal streamed over a WebSocket, so it
is usable directly in the page. This replaced a launcher that opened a GUI
terminal window on whatever machine ran the server, which was unreachable
whenever the browser was somewhere else and simply unavailable on a headless
host. POSIX uses the standard library's `pty` module; Windows uses
ConPTY via `pywinpty`. Both paths converge on the same `output_queue` /
`pump_output` machinery below, so the message loop and cleanup logic don't
need to branch on platform.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import hashlib
import os
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

try:
    # POSIX-only; core/web/server.py imports this router unconditionally,
    # so a top-level import failure here would crash the whole server on
    # Windows before pty_capability()'s own platform check ever runs.
    import fcntl
    import termios
except ImportError:  # pragma: no cover - exercised only on Windows
    fcntl = None  # type: ignore[assignment]
    termios = None  # type: ignore[assignment]

try:
    # Windows-only; see the try/except above for why this must not be a
    # top-level hard import.
    import winpty
except ImportError:  # pragma: no cover - exercised only on POSIX
    winpty = None  # type: ignore[assignment]

from core.constants import ENGINES
from core.host_env import child_environ
from core.logging_config import get_logger
from core.resource_locator import CODE_ROOT
from core.services.config_service import ConfigService
from core.services.resume_commands import is_safe_session_id, resume_command
from core.services.workspace_service import (
    WorkspaceConfigError,
    WorkspaceNotRegisteredError,
    WorkspaceResolutionError,
    resolve_registered_workspace,
)
from core.web.case_convert import ProtocolModel, camelize
from core.web.routers.config import get_config_path
from core.web.security import verify_websocket

router = APIRouter(prefix="/api/pty", tags=["pty"])
logger = get_logger(__name__)

_CA_LAUNCHER = CODE_ROOT / "ca_launcher.py"

_READ_CHUNK = 65536
_PTY_QUEUE_MAX_SIZE = 1024


def _enqueue_pty_output(
    queue: asyncio.Queue[bytes | str | None], item: bytes | str | None
) -> None:
    """Enqueues output chunk into queue, dropping oldest chunks if full to prevent OOM.

    Trade-off note: Dropping the oldest chunk when the queue is saturated prioritizes
    system stability and memory bounds over continuous terminal stream integrity.
    Discarding an arbitrary chunk may split an in-flight ANSI escape sequence or a
    multi-byte UTF-8 character boundary, potentially resulting in transient terminal
    rendering artifacts until the next redraw/clear. This is an intentional choice:
    preventing process crash / out-of-memory under slow client consumption takes
    precedence over lossless backlog preservation.
    """
    if item is None:
        while queue.full():
            try:
                queue.get_nowait()
            except (asyncio.QueueEmpty, ValueError):
                break
        try:
            queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        return

    if queue.full():
        try:
            queue.get_nowait()
            logger.warning(
                "PTY output queue full (%d items); dropped oldest chunk to prevent memory exhaustion",
                queue.maxsize,
            )
        except (asyncio.QueueEmpty, ValueError):
            pass
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        pass


# 伪引擎标识：engine=shell 时不拉起任何 Agent CLI，而是给用户一个纯系统
# shell（Windows 优先 Git Bash，兜底 PowerShell/cmd；POSIX 用 $SHELL）。
SHELL_ENGINE = "shell"

# ── tmux 承载（POSIX）────────────────────────────────────────────────────
#
# 关掉浏览器标签页不应杀掉正在干活的引擎：直接在 PTY 里跑引擎时，websocket
# 一断（关标签页）路由就只能 terminate 整个进程组。改为让引擎跑在一个专用
# tmux server 的独立会话里，PTY 里只跑 attach 客户端：
#
# - 关标签页 → 只杀 attach 客户端（等于 detach），引擎照跑；
# - 重开页面（同一 engine+cwd+session 深链，或实例页 attach_id）→ 重新
#   attach 回同一个引擎进程，TUI 状态与历史都在；
# - 实例页"停止" → kill-session，引擎真死；
# - 引擎自己退出 → pane-died 钩子 detach 客户端，尾部输出不丢（实验证明
#   不开 remain-on-exit 时 tmux 会截掉最后一屏）。
#
# 专用 socket（而非用户自己的 tmux server）保证 pane 环境继承自本服务、
# 且永远不会动到用户手头的 tmux 会话；服务关闭时 kill-server 收摊。

_TMUX_SOCKET_ENV = "CA_PTY_TMUX_SOCKET"
_DEFAULT_TMUX_SOCKET = "codeagent"

# 活跃 PTY 会话注册表，供实例管理页（routers/instances.py）列出与停止。
# 只在事件循环内读写，普通 dict 即可。
_ACTIVE_SESSIONS: dict[str, dict[str, Any]] = {}

# The browser tab id that names a fresh terminal's tmux session. It is only
# hashed, never passed to a shell, but a bounded charset keeps it a key.
_TAB_KEY_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_MIN_COLS, _MAX_COLS = 2, 1000
_MIN_ROWS, _MAX_ROWS = 2, 500

# 概览页启动引擎时带的首条提示。不放进 websocket 的 query：uvicorn 的访问日志
# 会记下整条 URL，提示词既可能很长，也可能含不想落进日志的内容。所以先 POST
# 到 /api/pty/prompt 暂存，再由同一个 tab_key 的 websocket 取走一次；取走即删，
# 一直没人取就在 TTL 后丢弃。
_PENDING_PROMPTS: dict[str, tuple[str, float]] = {}
_PROMPT_TTL_SECONDS = 60.0
_MAX_PROMPT_CHARS = 20_000


def _purge_expired_prompts(now: float) -> None:
    for key, (_prompt, stored_at) in list(_PENDING_PROMPTS.items()):
        if now - stored_at > _PROMPT_TTL_SECONDS:
            del _PENDING_PROMPTS[key]


def _stage_prompt(tab_key: str, prompt: str, *, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    _purge_expired_prompts(now)
    _PENDING_PROMPTS[tab_key] = (prompt, now)


def _take_prompt(tab_key: str | None, *, now: float | None = None) -> str | None:
    """Removes and returns the staged prompt for *tab_key*, if it is still fresh."""
    if tab_key is None:
        return None
    now = time.monotonic() if now is None else now
    _purge_expired_prompts(now)
    staged = _PENDING_PROMPTS.pop(tab_key, None)
    return staged[0] if staged else None


def _tmux_binary() -> str | None:
    """The tmux path, or None when POSIX-without-tmux / Windows."""
    if sys.platform == "win32":
        return None
    return shutil.which("tmux")


def _tmux_socket() -> str:
    """The dedicated tmux socket name (tests override via env)."""
    return os.environ.get(_TMUX_SOCKET_ENV, _DEFAULT_TMUX_SOCKET)


def _run_tmux(*args: str, timeout: float = 10) -> subprocess.CompletedProcess[str]:
    """Runs one tmux command on the dedicated socket, synchronously.

    The environment matches what a directly-spawned engine got (see
    _spawn_posix), so panes created on a fresh server inherit the same
    PATH/locale/credentials this server would have handed the engine.
    """
    binary = _tmux_binary()
    if binary is None:
        raise SpawnError("tmux is not available")
    return subprocess.run(
        [binary, "-L", _tmux_socket(), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _tmux_session_name(
    engine: str,
    working_dir: Path,
    session_id: str | None,
    tab_key: str | None = None,
) -> str:
    """The tmux session name for one browser terminal.

    Resumed engine sessions hash (engine, cwd, session id) so reopening the
    same deep link lands on the same running engine. A fresh terminal hashes
    the browser tab's own key instead: a reload or reconnect of that tab must
    land on the engine it already started, or every reconnect spawns another
    engine and strands the previous one in tmux. With neither, the name is
    unique so two tabs never share one engine.
    """
    if session_id:
        digest = hashlib.sha256(
            f"{engine}\0{working_dir}\0{session_id}".encode()
        ).hexdigest()[:12]
    elif tab_key:
        digest = hashlib.sha256(
            f"{engine}\0{working_dir}\0tab\0{tab_key}".encode()
        ).hexdigest()[:12]
    else:
        digest = uuid4().hex[:12]
    return f"ca-{engine}-{digest}"


def _tmux_ensure_session(
    name: str,
    engine_argv: list[str],
    working_dir: Path,
    cols: int = 80,
    rows: int = 24,
) -> None:
    """Creates the tmux session running *engine_argv* if it doesn't exist.

    The session is first created *without* a command (a default shell holds
    the pane), options are applied, and only then does ``respawn-pane -k``
    swap in the engine. Starting the engine with ``new-session`` itself had
    two problems, both reproduced with tmux 3.4: an engine that exits
    before the follow-up ``set-option`` calls ran left the session without
    `remain-on-exit`/the `pane-died` hook (the exit then went unnoticed),
    and an instantly-dying engine could hang the ``new-session`` client
    process itself forever, holding a ptmx.

    `remain-on-exit` + a `pane-died` hook keep the client's final screen
    (and the trailing output) intact and detach it cleanly when the engine
    exits; `status off` keeps the terminal looking native rather than
    wearing tmux's green bar. All option/hook calls are best-effort — an
    older tmux must still give a working, if uglier, terminal.
    """
    if _run_tmux("has-session", "-t", name).returncode == 0:
        return
    result = _run_tmux(
        "new-session",
        "-d",
        "-s",
        name,
        "-x",
        str(cols),
        "-y",
        str(rows),
        "-c",
        str(working_dir),
    )
    if result.returncode != 0:
        # Lost a create race with another connection: the winner is
        # responsible for the options and the engine, so attaching will
        # simply work.
        if _run_tmux("has-session", "-t", name).returncode == 0:
            return
        raise SpawnError(
            f"tmux new-session failed: {result.stderr.strip() or result.returncode}"
        )
    for args in (
        ("set-option", "-t", name, "remain-on-exit", "on"),
        # detach-client -s（按会话踢）而不是 -a：-a 是"除当前客户端外"，
        # hook 里没有当前客户端，等于一个都不踢（实验验证过）。
        # detach 放进 run-shell 里的子 tmux 客户端执行，而不是作为 hook
        # 命令直接跑：pane 在 attach 握手进行中死亡时，hook 里同步的
        # detach-client 会打在半初始化的客户端上而失效，客户端随后完成
        # 握手、永远挂在死 pane 上（间歇性复现）。run-shell 晚几毫秒，
        # 握手已结束，detach 稳定生效。
        (
            "set-hook",
            "-t",
            name,
            "pane-died",
            f"run-shell 'tmux -L {_tmux_socket()} detach-client -s {name}'",
        ),
        ("set-option", "-t", name, "status", "off"),
        ("set-option", "-t", name, "escape-time", "10"),
        ("set-option", "-t", name, "history-limit", "10000"),
    ):
        _run_tmux(*args)
    result = _run_tmux(
        "respawn-pane",
        "-k",
        "-t",
        name,
        "-c",
        str(working_dir),
        shlex.join(engine_argv),
    )
    if result.returncode != 0:
        with contextlib.suppress(Exception):
            _run_tmux("kill-session", "-t", name)
        raise SpawnError(
            f"tmux respawn-pane failed: {result.stderr.strip() or result.returncode}"
        )


def _tmux_has_session(name: str) -> bool:
    return _run_tmux("has-session", "-t", name).returncode == 0


def _tmux_engine_gone(name: str) -> bool:
    """True when the engine behind *name* no longer runs.

    A session whose pane died still exists (remain-on-exit) — that lingering
    state is exactly what preserves the final screen, so "gone" must check
    the pane, not the session.
    """
    result = _run_tmux("display-message", "-p", "-t", name, "#{pane_dead}")
    return result.returncode != 0 or result.stdout.strip() == "1"


def _tmux_kill_session(name: str) -> None:
    _run_tmux("kill-session", "-t", name)


def _tmux_pane_pid(name: str) -> int | None:
    result = _run_tmux("display-message", "-p", "-t", name, "#{pane_pid}")
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def kill_tmux_server() -> None:
    """Kills the dedicated tmux server (lifespan startup/shutdown hook).

    At startup it reaps sessions left by a crashed previous run; at shutdown
    it takes the engines down with the service that owns them, so terminals
    never outlive the server with no way to reach them.
    """
    if _tmux_binary() is None:
        return
    with contextlib.suppress(Exception):
        _run_tmux("kill-server", timeout=5)


# 看门狗：轮询服务进程，一消失就 kill-server。lifespan 的收尾只在一次
# Ctrl+C 这种体面退出时才跑；连按两次 Ctrl+C、关终端窗口（SIGHUP）、被
# kill 都会跳过它，而 tmux server 是独立守护进程，引擎会一直占着内存。
_TMUX_WATCHDOG_SCRIPT = (
    'while kill -0 "$1" 2>/dev/null; do sleep 2; done; '
    '"$2" -L "$3" kill-server 2>/dev/null'
)


def start_tmux_watchdog(pid: int | None = None) -> None:
    """Takes the tmux server down once *pid* (this process) is gone, however it died."""
    binary = _tmux_binary()
    if binary is None:
        return
    with contextlib.suppress(OSError):
        subprocess.Popen(
            [
                "/bin/sh",
                "-c",
                _TMUX_WATCHDOG_SCRIPT,
                "ca-tmux-watchdog",
                str(pid or os.getpid()),
                binary,
                _tmux_socket(),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # 自成会话：关终端窗口时发给整个进程组的 SIGHUP 不能把它也带走。
            start_new_session=True,
        )


def list_active_sessions() -> list[dict[str, Any]]:
    """返回活跃 PTY 会话的可序列化信息（不含会话对象本身）。"""
    return [
        {key: value for key, value in entry.items() if key != "session"}
        for entry in _ACTIVE_SESSIONS.values()
    ]


async def prune_detached_sessions() -> None:
    """Drops registry entries whose engine has exited while detached.

    A detached entry has no websocket of its own, so nothing else notices
    when its engine finishes; the instances poll calls this. Also kills the
    lingered tmux session (remain-on-exit keeps it around) so it doesn't
    leak.
    """
    for pty_id, entry in list(_ACTIVE_SESSIONS.items()):
        if entry.get("session") is not None:
            continue
        name = entry.get("tmux_name")
        if not name:
            continue
        if await asyncio.to_thread(_tmux_engine_gone, name):
            await asyncio.to_thread(_tmux_kill_session, name)
            _ACTIVE_SESSIONS.pop(pty_id, None)


def _entry_for_tmux_name(name: str) -> dict[str, Any] | None:
    for entry in _ACTIVE_SESSIONS.values():
        if entry.get("tmux_name") == name:
            return entry
    return None


async def stop_active_session(session_id: str) -> bool:
    """终止一个活跃 PTY 会话；不存在时返回 False。

    tmux 承载的会话必须 kill-session 才会真的停掉引擎——只 terminate
    attach 客户端等于 detach，引擎会继续跑。
    """
    entry = _ACTIVE_SESSIONS.get(session_id)
    if entry is None:
        return False
    session = entry.get("session")
    if session is not None:
        await session.shutdown()
    else:
        # Detached entry (tab closed, engine still running): no client to
        # terminate, the tmux session is the engine.
        name = entry.get("tmux_name")
        if name:
            await asyncio.to_thread(_tmux_kill_session, name)
    _ACTIVE_SESSIONS.pop(session_id, None)
    return True


def _shell_command() -> list[str]:
    """返回当前平台的交互式 shell 命令。"""
    if sys.platform != "win32":
        return [os.environ.get("SHELL") or "/bin/bash"]
    # 与 CodeBuddy 同样的策略：优先 Git Bash（从 git 的安装位置向上推导
    # Git 根目录，兼容 cmd/git.exe 与 mingw64/bin/git.exe 两种布局，
    # 同时避开 WSL 的 System32\bash.exe）。
    candidates: list[Path] = []
    git = shutil.which("git")
    if git:
        for ancestor in Path(git).parents:
            candidates.append(ancestor / "bin" / "bash.exe")
            candidates.append(ancestor / "usr" / "bin" / "bash.exe")
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if root:
            candidates.append(Path(root) / "Git" / "bin" / "bash.exe")
    for path in candidates:
        if path.is_file():
            return [str(path), "--login", "-i"]
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell:
        return [shell]
    return [os.environ.get("COMSPEC", "cmd.exe")]


def _engine_argv(
    engine: str,
    working_dir: Path,
    session_id: str | None,
    initial_prompt: str | None = None,
) -> list[str]:
    """What this PTY should run.

    Three shapes: a bare shell, a fresh engine session through
    ``ca_launcher.py`` (which injects prompts/skills/plugins), or an existing
    session handed straight back to its engine. The last one is why the
    endpoint takes a session id at all -- resuming used to mean opening a GUI
    terminal window on whatever machine happened to be running the server.

    *initial_prompt* only applies to the fresh-session shape, as the launcher's
    positional first message.
    """
    if engine == SHELL_ENGINE:
        return _shell_command()
    if session_id:
        return resume_command(engine, session_id, working_dir)
    argv = [sys.executable, str(_CA_LAUNCHER), engine]
    if initial_prompt and initial_prompt.strip():
        # The launcher (core.engine_base.launch_args.split_passthrough) reads a
        # lone argument as an engine flag or subcommand when it has no
        # whitespace -- "-x" or "resume" would be passed to the engine instead
        # of typed into it. A trailing space makes it plain text; the launcher
        # strips it again.
        argv.append(initial_prompt.strip() + " ")
    return argv


def pty_capability() -> dict:
    """Reports whether this server can attach a browser-streamed PTY."""
    if sys.platform == "win32" and winpty is None:
        return {
            "available": False,
            "reason": "pywinpty is not installed",
        }
    return {"available": True, "reason": None}


@router.get("/status")
async def get_pty_status() -> dict:
    return pty_capability()


class StagePromptRequest(ProtocolModel):
    tab_key: str
    prompt: str


@router.post("/prompt")
async def stage_initial_prompt(body: StagePromptRequest) -> dict:
    """Holds the first message for the terminal about to open under *tab_key*.

    The websocket for that tab picks it up when it starts a fresh engine
    session. A tab that reconnects to a terminal still running in tmux never
    consumes it, so a reload cannot type the prompt a second time.
    """
    if not _TAB_KEY_RE.fullmatch(body.tab_key):
        raise HTTPException(status_code=400, detail="Malformed tab key")
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Empty prompt")
    if len(body.prompt) > _MAX_PROMPT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt is longer than {_MAX_PROMPT_CHARS} characters",
        )
    _stage_prompt(body.tab_key, body.prompt)
    return {"success": True}


@router.get("/sessions")
async def list_pty_sessions() -> dict:
    """活跃 PTY 会话列表，供实例管理页使用。"""
    # 内部注册表 _ACTIVE_SESSIONS 仍是 snake_case，因为 instances.py 也按
    # Python 的读法取它的字段；camelize 只作用在出网这一层。
    return {"sessions": [camelize(entry) for entry in list_active_sessions()]}


@router.post("/sessions/{session_id}/stop")
async def stop_pty_session(session_id: str) -> dict:
    return {"success": await stop_active_session(session_id)}


@router.post("/close")
async def close_pty_terminal(
    engine: str = Query(...),
    cwd: str = Query(...),
    session_id: str | None = Query(None),
    tab_key: str | None = Query(None),
) -> dict:
    """Stops the engine behind a browser terminal tab the user closed.

    Dropping the websocket only detaches (a reload must not kill work in
    progress), so without this every closed tab left its engine running in
    tmux until the server stopped -- a few hundred MB each.
    """
    if tab_key is not None and not _TAB_KEY_RE.fullmatch(tab_key):
        raise HTTPException(status_code=400, detail="Malformed tab key")
    if session_id is None and tab_key is None:
        # A unique-named terminal can't be found again by its parameters.
        return {"success": False}
    if _tmux_binary() is None:
        return {"success": False}
    try:
        working_dir = _resolve_registered_workspace(cwd)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    name = _tmux_session_name(engine, working_dir, session_id, tab_key)
    entry = _entry_for_tmux_name(name)
    if entry is not None:
        return {"success": await stop_active_session(entry["id"])}
    probe = await asyncio.to_thread(_run_tmux, "has-session", "-t", name)
    if probe.returncode != 0:
        return {"success": False}
    await asyncio.to_thread(_tmux_kill_session, name)
    return {"success": True}


def _resolve_registered_workspace(cwd: str) -> Path:
    """The directory this terminal may open in.

    Delegates rather than comparing paths itself: this used to require an
    exact registry match, so a terminal could not be opened in a subdirectory
    of a registered project even though the agent gateway happily started a
    session there. Resuming a session lands here too, and those sessions
    routinely live in subdirectories.
    """
    try:
        registered = resolve_registered_workspace(
            ConfigService(get_config_path()), cwd, interactive=True
        )
    except WorkspaceNotRegisteredError as exc:
        # Only reachable off loopback now -- on a local bind any existing
        # directory resolves. See core.services.workspace_service.
        raise ValueError(
            f"{cwd} is not a registered workspace, which this server requires "
            "because it is reachable from the network"
        ) from exc
    except WorkspaceResolutionError as exc:
        # "not a directory" / "invalid path" -- say which one, and which path.
        raise ValueError(f"{cwd}: {exc}") from exc
    except WorkspaceConfigError as exc:
        raise ValueError(str(exc)) from exc
    return Path(registered.path)


# ── Uniform session interface ─────────────────────────────────────────────
#
# The websocket handler below is written once against this interface; the
# POSIX and Windows implementations each push decoded output text into the
# same `output_queue` (POSIX pushes raw bytes through an incremental UTF-8
# decoder in pump_output; Windows' `PtyProcess.read()` already returns
# decoded str, so its chunks skip that decoder) and post `None` to signal
# EOF, exactly like the original POSIX-only implementation did.


class PtySession(Protocol):
    def write(self, data: str) -> None: ...
    def resize(self, cols: int, rows: int) -> None: ...
    @property
    def pid(self) -> int | None: ...
    async def wait(self) -> int:
        """Blocks until the child exits and returns its exit code."""
        ...

    async def terminate(self) -> None: ...

    async def shutdown(self) -> None:
        """Stops the engine itself, not just the attach client."""
        ...

    async def kill(self) -> None: ...
    async def close(self) -> None: ...
    @property
    def returncode(self) -> int | None: ...


class SpawnError(Exception):
    """Raised when a PTY session could not be started."""


def _resize_fd(fd: int, cols: int, rows: int) -> None:
    with contextlib.suppress(OSError):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))  # type: ignore[attr-defined]


def _tmux_resize_window(name: str | None, cols: int, rows: int) -> None:
    if not name:
        return
    with contextlib.suppress(Exception):
        _run_tmux("resize-window", "-t", name, "-x", str(cols), "-y", str(rows))


class _PosixSession:
    def __init__(
        self,
        process,
        master_fd: int,
        tmux_name: str | None = None,
    ):
        self._process = process
        self._master_fd = master_fd
        # Set when the process is a `tmux attach-session` client rather
        # than the engine itself: terminating this process then only
        # detaches, while shutdown() kills the engine's tmux session.
        self.tmux_name = tmux_name

    @property
    def pid(self) -> int | None:
        return self._process.pid

    def write(self, data: str) -> None:
        with contextlib.suppress(OSError):
            os.write(self._master_fd, data.encode())

    def resize(self, cols: int, rows: int) -> None:
        _resize_fd(self._master_fd, cols, rows)
        _tmux_resize_window(self.tmux_name, cols, rows)

    async def wait(self) -> int:
        return await self._process.wait()

    def _signal_process_group(self, sig: int) -> None:
        """Signals the whole process group, not just the tracked child.

        ``_spawn_posix`` passes ``start_new_session=True``, so the child is a
        process-group leader and the engine CLI it execs is a *grandchild*.
        Signalling only the tracked pid leaves that grandchild running with no
        terminal attached, and the launcher never gets to undo what it
        injected into the workspace. The Windows path already kills the tree
        for the same reason.
        """
        pid = self._process.pid
        if pid is None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            # POSIX-only, like the class holding it and the ioctl above.
            os.killpg(os.getpgid(pid), sig)  # type: ignore[attr-defined]

    async def terminate(self) -> None:
        self._signal_process_group(signal.SIGTERM)

    async def kill(self) -> None:
        # SIGKILL 只存在于 POSIX；本类和上面的 ioctl 一样只在 POSIX 下实例化，
        # 但 mypy 在 Windows 上跑时看不到 spawn 处的平台守卫。
        self._signal_process_group(signal.SIGKILL)  # type: ignore[attr-defined]

    async def shutdown(self) -> None:
        if self.tmux_name:
            await asyncio.to_thread(_tmux_kill_session, self.tmux_name)
        await self.terminate()  # type: ignore[attr-defined]

    async def close(self) -> None:
        with contextlib.suppress(OSError):
            os.close(self._master_fd)

    @property
    def returncode(self) -> int | None:
        return self._process.returncode


async def _spawn_posix(
    engine: str,
    working_dir: Path,
    output_queue: asyncio.Queue[bytes | str | None],
    session_id: str | None = None,
    *,
    tmux_name: str | None = None,
    tab_key: str | None = None,
    cols: int = 80,
    rows: int = 24,
    initial_prompt: str | None = None,
) -> _PosixSession:
    """Spawns what the browser terminal drives.

    With tmux available the engine runs inside a tmux session on the
    dedicated socket and the PTY hosts ``tmux attach-session`` instead, so a
    dropped websocket detaches rather than kills (see the tmux block comment
    at the top of this module). *tmux_name*, when given, is an existing
    session to attach to — created sessions are cleaned up again if the
    attach client itself fails to spawn.
    """
    import pty  # POSIX-only; imported lazily so the module still loads on Windows.

    master_fd, slave_fd = pty.openpty()  # type: ignore[attr-defined]
    # The engine starts at this size. Starting at 80x24 and resizing once the
    # socket opens races the engine's own startup: a TUI that draws before
    # its SIGWINCH handler is in place stays drawn at 80x24.
    _resize_fd(master_fd, cols=cols, rows=rows)
    env = {
        **child_environ(),
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }

    created_tmux_name: str | None = None
    try:
        try:
            engine_argv = _engine_argv(engine, working_dir, session_id, initial_prompt)
            binary = _tmux_binary()
            if binary is None:
                # tmux unavailable (or Windows): run the engine directly,
                # exactly like the pre-tmux behavior -- closing the tab then
                # terminates it.
                tmux_name = None
                argv = engine_argv
            else:
                if tmux_name is None:
                    tmux_name = _tmux_session_name(
                        engine, working_dir, session_id, tab_key
                    )
                    created_tmux_name = tmux_name
                    await asyncio.to_thread(
                        _tmux_ensure_session,
                        tmux_name,
                        engine_argv,
                        working_dir,
                        cols,
                        rows,
                    )
                argv = [binary, "-L", _tmux_socket(), "attach-session", "-t", tmux_name]
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=str(working_dir),
                env=env,
                start_new_session=True,
            )
        finally:
            os.close(slave_fd)
    except BaseException as exc:
        # Spawn failed (e.g. out of file descriptors/processes, or the tmux
        # session could not be created) or the await was cancelled (e.g. the
        # client vanished mid-connect -- raised as asyncio.CancelledError, a
        # BaseException, not an Exception, so it must be caught here too).
        # Either way the slave fd is already closed above, but master_fd was
        # opened before this try and nothing else owns it yet, so it must be
        # closed here or it leaks for the life of the server process.
        with contextlib.suppress(OSError):
            os.close(master_fd)
        if created_tmux_name is not None:
            # We created the tmux session above; with no attach client
            # coming, that engine would run forever unreached.
            with contextlib.suppress(Exception):
                await asyncio.to_thread(_tmux_kill_session, created_tmux_name)
        # Only a genuine spawn failure (OSError/SpawnError) becomes a clean
        # websocket close via SpawnError -- cancellation must propagate
        # unwrapped so it keeps behaving like real task cancellation for the
        # caller.
        if not isinstance(exc, (OSError, SpawnError)):
            raise
        raise SpawnError(str(exc)) from exc

    loop = asyncio.get_running_loop()

    def _on_readable() -> None:
        try:
            chunk = os.read(master_fd, _READ_CHUNK)
        except OSError:
            chunk = b""
        if not chunk:
            with contextlib.suppress(ValueError):
                loop.remove_reader(master_fd)
            _enqueue_pty_output(output_queue, None)
            return
        _enqueue_pty_output(output_queue, chunk)

    loop.add_reader(master_fd, _on_readable)
    return _PosixSession(process, master_fd, tmux_name=tmux_name)


class _WindowsSession:  # pragma: no cover - exercised only on Windows
    def __init__(self, pty_process, loop: asyncio.AbstractEventLoop, output_queue):
        self._pty = pty_process
        self._loop = loop
        self._queue = output_queue
        self._returncode: int | None = None
        # Set by close() before it tears down the pty, so the reader thread
        # (whose blocking read() unblocks once the pty closes) knows not to
        # post into a queue tied to a loop that may already be shutting
        # down, rather than racing that shutdown.
        self._closing = threading.Event()
        self._reader_thread = threading.Thread(
            target=self._read_loop, daemon=True, name="pty-windows-reader"
        )
        self._reader_thread.start()

    @property
    def pid(self) -> int | None:
        return self._pty.pid

    def _read_loop(self) -> None:
        consecutive_errors = 0
        while True:
            try:
                data = self._pty.read(_READ_CHUNK)
                consecutive_errors = 0
            except EOFError:
                data = ""
            except Exception as exc:
                if self._closing.is_set():
                    return
                consecutive_errors += 1
                logger.warning(
                    "Unexpected error reading from Windows PTY (retry %d): %s",
                    consecutive_errors,
                    exc,
                )
                is_alive = getattr(self._pty, "isalive", lambda: True)()
                if not is_alive or consecutive_errors >= 5:
                    logger.error(
                        "Windows PTY process is not alive or exceeded error threshold; stopping reader."
                    )
                    data = ""
                else:
                    time.sleep(0.05)
                    continue
            if self._closing.is_set():
                return
            with contextlib.suppress(RuntimeError):
                self._loop.call_soon_threadsafe(
                    _enqueue_pty_output, self._queue, data or None
                )
            if not data:
                return

    def write(self, data: str) -> None:
        with contextlib.suppress(Exception):
            self._pty.write(data)

    def resize(self, cols: int, rows: int) -> None:
        with contextlib.suppress(Exception):
            self._pty.setwinsize(rows, cols)

    async def wait(self) -> int:
        # PtyProcess.wait() blocks the calling thread, so it must run off
        # the event loop -- otherwise it would stall every other
        # connection/request this server is handling until the child exits.
        code = await asyncio.to_thread(self._pty.wait)
        self._returncode = code if isinstance(code, int) else 0
        return self._returncode

    async def _kill_process_tree(self) -> None:
        # PtyProcess.terminate() only signals the one PID it directly
        # spawned. On this and apparently many Windows Python setups,
        # sys.executable is a thin relauncher that immediately re-execs a
        # child process to run the real interpreter -- killing just the
        # tracked PID leaves that child (the one actually running the
        # engine) orphaned and still running. `taskkill /T` kills the whole
        # tree, so it's used unconditionally rather than trusting
        # PtyProcess's own single-PID terminate/kill.
        pid = self._pty.pid
        if pid is None:
            return
        with contextlib.suppress(Exception):
            await asyncio.to_thread(
                subprocess.run,
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )

    async def terminate(self) -> None:
        await self._kill_process_tree()

    async def shutdown(self) -> None:
        # ConPTY has no tmux layer: the engine IS the spawned process.
        await self._kill_process_tree()

    async def kill(self) -> None:
        await self._kill_process_tree()

    async def close(self) -> None:
        self._closing.set()
        with contextlib.suppress(Exception):
            await asyncio.to_thread(self._pty.close, True)
        # Wait for the reader thread to actually exit (its blocking read()
        # call unblocks once the pty closes above) so it can't outlive this
        # coroutine and post into a queue tied to a loop that's already
        # shutting down.
        await asyncio.to_thread(self._reader_thread.join, 3)

    @property
    def returncode(self) -> int | None:
        if self._returncode is not None:
            return self._returncode
        with contextlib.suppress(Exception):
            if not self._pty.isalive():
                self._returncode = self._pty.exitstatus or 0
        return self._returncode


async def _spawn_windows(  # pragma: no cover - exercised only on Windows
    engine: str,
    working_dir: Path,
    output_queue: asyncio.Queue[bytes | str | None],
    session_id: str | None = None,
    cols: int = 80,
    rows: int = 24,
    initial_prompt: str | None = None,
) -> _WindowsSession:
    loop = asyncio.get_running_loop()
    env = {**child_environ(), "TERM": "xterm-256color"}
    argv = _engine_argv(engine, working_dir, session_id, initial_prompt)
    try:
        # PtyProcess.spawn() does a PATH lookup + creates the ConPTY
        # synchronously; it's fast, but run it off-thread anyway so a slow
        # PATH lookup on a loaded machine can't stall the event loop.
        pty_process = await asyncio.to_thread(
            winpty.PtyProcess.spawn,
            argv,
            cwd=str(working_dir),
            env=env,
            dimensions=(rows, cols),
        )
    except Exception as exc:
        raise SpawnError(str(exc)) from exc
    return _WindowsSession(pty_process, loop, output_queue)


@router.websocket("/ws")
async def pty_websocket(
    websocket: WebSocket,
    engine: str = Query(...),
    cwd: str = Query(...),
    session_id: str | None = Query(
        None,
        description="Resume this existing session instead of starting a new one",
    ),
    attach_id: str | None = Query(
        None,
        description="Attach to a live browser terminal from /api/pty/sessions",
    ),
    tab_key: str | None = Query(
        None,
        description="The browser tab's own id; reconnects of it reattach",
    ),
    cols: int = Query(80, ge=_MIN_COLS, le=_MAX_COLS),
    rows: int = Query(24, ge=_MIN_ROWS, le=_MAX_ROWS),
) -> None:
    # Authenticate before anything else: this endpoint hands the caller an
    # interactive shell, and a WebSocket handshake is not subject to the
    # same-origin policy, so without this any page the user visits could
    # open one. verify_websocket() closes the socket itself on failure.
    if not await verify_websocket(websocket):
        return
    # Accept before the remaining checks so their close frames carry a reason
    # the browser can actually read. A close *before* the handshake completes
    # is just a rejected upgrade: the reason never reaches JavaScript, which
    # is why an unusable cwd or a missing engine used to surface as a bare
    # "connection closed" with nothing to act on. Authentication stays above
    # this line -- an unauthenticated caller gets no socket at all.
    await websocket.accept()

    capability = pty_capability()
    if not capability["available"]:
        await websocket.close(code=1013, reason=capability["reason"])
        return
    if engine != SHELL_ENGINE and engine not in ENGINES:
        await websocket.close(code=4400, reason=f"Unknown engine: {engine}")
        return
    if session_id is not None:
        # The id becomes an argv element. Nothing reaches a shell, but one
        # starting with "-" would be read by the engine CLI as a flag.
        if engine == SHELL_ENGINE:
            await websocket.close(
                code=4400, reason="A plain shell has no session to resume"
            )
            return
        if not is_safe_session_id(session_id):
            await websocket.close(code=4400, reason="Malformed session id")
            return
    if tab_key is not None and not _TAB_KEY_RE.fullmatch(tab_key):
        await websocket.close(code=4400, reason="Malformed tab key")
        return
    attach_tmux_name: str | None = None
    if attach_id is not None:
        entry = _ACTIVE_SESSIONS.get(attach_id)
        if (
            entry is None
            or not isinstance(entry.get("tmux_name"), str)
            or not entry["tmux_name"]
        ):
            await websocket.close(
                code=4404, reason="The terminal to attach to was not found"
            )
            return
        if await asyncio.to_thread(_tmux_engine_gone, entry["tmux_name"]):
            # The engine already exited; the lingered tmux session is just
            # its final screen. Take the stale entry down with it.
            await asyncio.to_thread(_tmux_kill_session, entry["tmux_name"])
            _ACTIVE_SESSIONS.pop(attach_id, None)
            await websocket.close(
                code=4404, reason="That terminal's engine has already exited"
            )
            return
        attach_tmux_name = entry["tmux_name"]
    try:
        working_dir = _resolve_registered_workspace(cwd)
    except ValueError as exc:
        await websocket.close(code=4400, reason=str(exc))
        return

    output_queue: asyncio.Queue[bytes | str | None] = asyncio.Queue(
        maxsize=_PTY_QUEUE_MAX_SIZE
    )

    # Only a brand-new engine session can take a first message: a resumed
    # session already has its conversation, a shell has no first message, and
    # attaching to a live terminal starts nothing.
    initial_prompt = (
        _take_prompt(tab_key)
        if session_id is None and engine != SHELL_ENGINE and attach_tmux_name is None
        else None
    )

    try:
        if sys.platform == "win32":  # pragma: no cover - exercised only on Windows
            session: PtySession = await _spawn_windows(
                engine,
                working_dir,
                output_queue,
                session_id,
                cols,
                rows,
                initial_prompt,
            )
        else:
            session = await _spawn_posix(
                engine,
                working_dir,
                output_queue,
                session_id,
                tmux_name=attach_tmux_name,
                tab_key=tab_key,
                cols=cols,
                rows=rows,
                initial_prompt=initial_prompt,
            )
    except SpawnError as exc:
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason=f"Failed to start session: {exc}")
        return

    # One registry entry per tmux session (per engine process), not per
    # websocket: a second connection attaching to the same running terminal
    # is a guest that must not duplicate the instances-page row, and a
    # reattach to a detached terminal takes the entry over so exactly one
    # owner is responsible for stop/prune at any time.
    owner_entry_id: str | None = None
    tmux_name = getattr(session, "tmux_name", None)
    if tmux_name:
        existing = _entry_for_tmux_name(tmux_name)
        if existing is not None and existing.get("session") is not None:
            pass  # live owner still attached; this connection is a guest
        else:
            if existing is None:
                owner_entry_id = uuid4().hex
                existing = {
                    "id": owner_entry_id,
                    "engine": engine,
                    "cwd": str(working_dir),
                    "resumed_session_id": session_id,
                    "pid": session.pid,
                    "started_at": datetime.now(UTC).isoformat(),
                    "tmux_name": tmux_name,
                    "detached": False,
                }
                _ACTIVE_SESSIONS[owner_entry_id] = existing
            else:
                owner_entry_id = existing["id"]
            existing["session"] = session
            existing["detached"] = False
            existing["pid"] = (
                await asyncio.to_thread(_tmux_pane_pid, tmux_name)
            ) or session.pid
    else:
        owner_entry_id = uuid4().hex
        _ACTIVE_SESSIONS[owner_entry_id] = {
            "id": owner_entry_id,
            "engine": engine,
            "cwd": str(working_dir),
            "resumed_session_id": session_id,
            "pid": session.pid,
            "started_at": datetime.now(UTC).isoformat(),
            "tmux_name": None,
            "detached": False,
            "session": session,
        }

    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    async def pump_output() -> None:
        while True:
            chunk = await output_queue.get()
            if chunk is None:
                return
            text = decoder.decode(chunk) if isinstance(chunk, bytes) else chunk
            with contextlib.suppress(Exception):
                await websocket.send_json({"type": "output", "data": text})

    process_exited = asyncio.Event()

    async def pump_exit() -> None:
        returncode = await session.wait()
        # The reader (POSIX: _on_readable, Windows: _read_loop) signals
        # pump_output itself once it sees real EOF. Wait for that natural
        # drain here (shielded so our own timeout below can't cancel it)
        # instead of tearing things down right away, or any output still
        # buffered when the process exits would race with -- and often
        # lose to -- this task, truncating the tail of the output. Bounded
        # in case an orphaned descendant still holds the pty open and EOF
        # never naturally arrives.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(output_task), timeout=2)
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "exit", "code": returncode})
        process_exited.set()

    output_task = asyncio.create_task(pump_output())
    exit_task = asyncio.create_task(pump_exit())
    exit_wait_task = asyncio.create_task(process_exited.wait())

    # 兜底：pane-died hook 正常会在引擎退出时 detach 我们的 attach 客户端
    # （客户端退出 → pump_exit → exit 消息）。但 hook 的 detach 偶尔会打
    # 在还没完成 attach 握手/仍在重绘的客户端上而失效，客户端就永远挂
    # 在死 pane 上，浏览器永远等不到"会话已结束"。轮询 pane 状态做保险。
    async def watch_engine_gone() -> None:
        assert tmux_name is not None
        while True:
            await asyncio.sleep(2)
            try:
                gone = await asyncio.to_thread(_tmux_engine_gone, tmux_name)
            except Exception:
                return  # tmux 不可用等异常：交给正常退出路径
            if gone:
                # 此时客户端早已完成握手，显式 detach 能成功且退出码为 0；
                # 直接 SIGTERM 会让浏览器把正常结束读成 code 1。
                for _ in range(3):
                    with contextlib.suppress(Exception):
                        await asyncio.to_thread(
                            _run_tmux, "detach-client", "-s", tmux_name
                        )
                    await asyncio.sleep(0.3)
                    if session.returncode is not None:
                        return
                if session.returncode is None:
                    await session.terminate()
                return

    engine_watch_task = asyncio.create_task(watch_engine_gone()) if tmux_name else None

    try:
        while not process_exited.is_set():
            receive_task = asyncio.ensure_future(websocket.receive_json())
            wait_set = {receive_task, exit_wait_task}
            if engine_watch_task is not None:
                wait_set.add(engine_watch_task)
            done, pending = await asyncio.wait(
                wait_set, return_when=asyncio.FIRST_COMPLETED
            )
            if exit_wait_task in done or (
                engine_watch_task is not None and engine_watch_task in done
            ):
                # watch_engine_gone 先于 pump_exit 结束时（pane-died hook 偶尔
                # detach 不中，靠 2s 轮询兜底），pump_exit 才刚拿到 returncode，
                # 还在等输出排空——它最多再花 2s 才会发 exit。这里若直接进清理，
                # 清理会 cancel exit_task，浏览器永远收不到退出码，只能把一个
                # 正常结束读成"连接断开"。等它落地，超时兜底防止真的挂住。
                if not process_exited.is_set():
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(
                            asyncio.shield(exit_wait_task), timeout=5
                        )
                receive_task.cancel()
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await receive_task
                break
            message = receive_task.result()
            if not isinstance(message, dict):
                continue
            kind = message.get("type")
            if kind == "input":
                data = message.get("data")
                if isinstance(data, str):
                    session.write(data)
            elif kind == "resize":
                new_cols, new_rows = message.get("cols"), message.get("rows")
                if isinstance(new_cols, int) and isinstance(new_rows, int):
                    session.resize(new_cols, new_rows)
    except WebSocketDisconnect:
        pass
    finally:
        # 整段清理放进被 shield 的独立任务：TestClient/anyio（部分网关
        # 亦然）在 ws 会话退出时会取消 handler 任务，清理链上第一个裸
        # await 就会被打断——engine_gone 查完之后的一切（detach 标记、
        # attach 客户端终止、fd 关闭）都不会执行。取消落在 shield 上，
        # 已启动的清理继续跑完。
        async def _cleanup_terminal() -> None:
            if engine_watch_task is not None:
                engine_watch_task.cancel()
            if owner_entry_id is not None:
                entry = _ACTIVE_SESSIONS.get(owner_entry_id)
                if entry is not None:
                    name = entry.get("tmux_name")
                    if not name:
                        # No tmux layer: the spawned process was the engine
                        # itself, so it's gone with this connection.
                        _ACTIVE_SESSIONS.pop(owner_entry_id, None)
                    elif await asyncio.to_thread(_tmux_engine_gone, name):
                        # The engine exited (our attach client was detached
                        # by the pane-died hook). Kill the lingered session
                        # -- remain-on-exit keeps it around holding the final
                        # screen -- and drop the registry row.
                        await asyncio.to_thread(_tmux_kill_session, name)
                        _ACTIVE_SESSIONS.pop(owner_entry_id, None)
                    else:
                        # The tab closed on a running engine: detach only.
                        # The terminal stays stoppable and reattachable from
                        # the instances page until its engine exits.
                        entry["detached"] = True
                        entry["session"] = None
                        entry["pid"] = (
                            await asyncio.to_thread(_tmux_pane_pid, name)
                        ) or entry.get("pid")
            exit_wait_task.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await exit_wait_task
            if session.returncode is None:
                await session.terminate()
                try:
                    await asyncio.wait_for(session.wait(), timeout=3)
                except TimeoutError:
                    await session.kill()
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(session.wait(), timeout=5)
            exit_task.cancel()
            output_task.cancel()
            await asyncio.gather(exit_task, output_task, return_exceptions=True)
            await session.close()
            with contextlib.suppress(Exception):
                await websocket.close()

        cleanup_task = asyncio.create_task(_cleanup_terminal())
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            # 外部取消：清理任务已在事件循环上，继续跑完。
            pass
