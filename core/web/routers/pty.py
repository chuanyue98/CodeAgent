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
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from core.constants import ENGINES
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
from core.web.pty import (
    _ACTIVE_SESSIONS,
    _DEFAULT_TMUX_SOCKET,
    _MAX_COLS,
    _MAX_PROMPT_CHARS,
    _MAX_ROWS,
    _MIN_COLS,
    _MIN_ROWS,
    _PENDING_PROMPTS,
    _PROMPT_TTL_SECONDS,
    _PTY_QUEUE_MAX_SIZE,
    _TAB_KEY_RE,
    _TMUX_SOCKET_ENV,
    SHELL_ENGINE,
    PtySession,
    SpawnError,
    _enqueue_pty_output,
    _entry_for_tmux_name,
    _PosixSession,
    _purge_expired_prompts,
    _resize_fd,
    _run_tmux,
    _spawn_posix,
    _spawn_windows,
    _stage_prompt,
    _take_prompt,
    _tmux_binary,
    _tmux_engine_gone,
    _tmux_ensure_session,
    _tmux_has_session,
    _tmux_kill_session,
    _tmux_pane_pid,
    _tmux_resize_window,
    _tmux_session_name,
    _tmux_socket,
    _WindowsSession,
    kill_tmux_server,
    list_active_sessions,
    prune_detached_sessions,
    start_tmux_watchdog,
    stop_active_session,
    winpty,
)
from core.web.routers.config import get_config_path
from core.web.security import verify_websocket

__all__ = [
    "PtySession",
    "SHELL_ENGINE",
    "SpawnError",
    "_ACTIVE_SESSIONS",
    "_DEFAULT_TMUX_SOCKET",
    "_MAX_COLS",
    "_MAX_PROMPT_CHARS",
    "_MAX_ROWS",
    "_MIN_COLS",
    "_MIN_ROWS",
    "_PENDING_PROMPTS",
    "_PROMPT_TTL_SECONDS",
    "_PTY_QUEUE_MAX_SIZE",
    "_PosixSession",
    "_TAB_KEY_RE",
    "_TMUX_SOCKET_ENV",
    "_WindowsSession",
    "_enqueue_pty_output",
    "_entry_for_tmux_name",
    "_purge_expired_prompts",
    "_resize_fd",
    "_run_tmux",
    "_spawn_posix",
    "_spawn_windows",
    "_stage_prompt",
    "_take_prompt",
    "_tmux_binary",
    "_tmux_engine_gone",
    "_tmux_ensure_session",
    "_tmux_has_session",
    "_tmux_kill_session",
    "_tmux_pane_pid",
    "_tmux_resize_window",
    "_tmux_session_name",
    "_tmux_socket",
    "get_config_path",
    "kill_tmux_server",
    "list_active_sessions",
    "prune_detached_sessions",
    "router",
    "start_tmux_watchdog",
    "stop_active_session",
    "winpty",
]

router = APIRouter(prefix="/api/pty", tags=["pty"])
logger = get_logger(__name__)

_CA_LAUNCHER = CODE_ROOT / "ca_launcher.py"

_READ_CHUNK = 65536


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
