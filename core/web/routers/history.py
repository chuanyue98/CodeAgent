"""Web API router for cross-engine session history browsing.

Endpoints:
  GET  /api/history?project=<path>&engine=<engine>
      List session summaries across all (or one) engine(s)

  GET  /api/history/audit?engine=&project=&since=&until=&limit=
      Flattened, time-sorted message/tool-call event timeline across
      sessions (and, if project is omitted, across all projects)

  GET  /api/history/{engine}/{session_id}?project=<path>
      Get full session detail with all messages

  POST /api/history/convert
      Convert a session from one engine format to another and write it
      to the target engine's session storage

  POST /api/history/convert-and-launch
      Convert a session and then launch the target engine with it
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import field_validator

from core.constants import ENGINES
from core.services.config_service import ConfigService
from core.services.resume_commands import resume_command
from core.services.workspace_service import (
    WorkspaceConfigError,
    WorkspaceResolutionError,
    resolve_registered_workspace,
)
from core.session_history.audit import build_audit_events
from core.session_history.session_finder import (
    find_all_sessions,
    find_session_by_id,
)
from core.web.case_convert import ProtocolModel, wire
from core.web.routers.config import get_config_path

router = APIRouter(prefix="/api")


def _validate_source_file_path(source_file: str, engine: str) -> Path:
    """Validates that *source_file* resides within the allowed engine history
    directory, preventing path-traversal attacks via a tampered JSONL field.

    Raises:
        HTTPException(400): If the path is empty or does not exist.
        HTTPException(403): If the resolved path escapes the allowed directory.
    """
    if not source_file:
        raise HTTPException(
            status_code=400,
            detail={"error": "Session source file path is empty"},
        )

    home = Path.home()
    file_path = Path(source_file).resolve()

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=400,
            detail={"error": f"Session source file path is invalid: {source_file}"},
        )

    allowed_dirs: list[Path] = []
    if engine == "claude":
        allowed_dirs.append((home / ".claude" / "projects").resolve())
    elif engine == "codex":
        allowed_dirs.append((home / ".codex" / "sessions").resolve())
    elif engine == "opencode":
        allowed_dirs.append((home / ".opencode").resolve())
        allowed_dirs.append((home / ".local" / "share" / "opencode").resolve())
    elif engine == "codebuddy":
        allowed_dirs.append((home / ".codebuddy" / "projects").resolve())

    for allowed in allowed_dirs:
        if file_path.is_relative_to(allowed):
            return file_path

    raise HTTPException(
        status_code=403,
        detail={
            "error": "Source file path is outside allowed engine history directories",
        },
    )


def _parse_ts(ts: str) -> datetime:
    """Parse ISO 8601 timestamp string to a UTC-aware datetime for comparison."""
    try:
        normalized = ts.replace("Z", "+00:00") if ts else ""
        dt = datetime.fromisoformat(normalized) if normalized else datetime.min
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=UTC)


class ConvertRequest(ProtocolModel):
    """Request body for cross-engine session conversion."""

    source_engine: str
    session_id: str
    target_engine: str
    project_path: str

    @field_validator("source_engine", "target_engine")
    @classmethod
    def validate_engine(cls, v: str) -> str:
        if v not in ENGINES:
            raise ValueError(
                f"Invalid engine '{v}'. Must be one of: {', '.join(sorted(ENGINES))}"
            )
        return v


class ConvertResponse(ProtocolModel):
    status: str
    new_session_id: str
    target_engine: str
    message: str | None = None


class ConvertAndLaunchResponse(ConvertResponse):
    #: Where the caller should attach a browser PTY. The session is not
    #: started here -- the websocket does that when the terminal opens.
    engine: str | None = None
    session_id: str | None = None
    project: str | None = None


class DeleteSessionResponse(ProtocolModel):
    status: str
    session_id: str


# The domain's own to_summary_dict()/to_full_dict()/to_dict() stay snake_case:
# they are Python-side serializations used by the CLI and tests. These models
# are the wire shape, and the only place the two vocabularies meet.


class ToolCall(ProtocolModel):
    name: str
    args_preview: str
    result_preview: str


class SessionMessage(ProtocolModel):
    role: str
    content: str
    timestamp: str
    model: str = ""
    tool_calls: list[ToolCall] = []


class SessionSummary(ProtocolModel):
    session_id: str
    engine: str
    project_path: str
    started_at: str
    ended_at: str
    message_count: int
    title: str
    model: str = ""
    source_file: str = ""


class SessionDetail(SessionSummary):
    messages: list[SessionMessage] = []


class ResumeTarget(ProtocolModel):
    status: str
    engine: str
    session_id: str
    project: str


class AuditEvent(ProtocolModel):
    """One row of the flattened timeline.

    Message and tool-call rows carry different halves of the optional fields;
    they are sent with ``drop_none`` so neither variant ships the other's
    nulls across a response that can hold thousands of rows.
    """

    event_id: str
    event_type: str
    engine: str
    project_path: str
    session_id: str
    session_title: str
    timestamp: str
    role: str
    model: str = ""
    content_preview: str | None = None
    tool_name: str | None = None
    args_preview: str | None = None
    result_preview: str | None = None


@router.get("/history")
async def list_sessions(
    project: str | None = Query(
        None, description="Project directory path; omit to search all projects"
    ),
    engine: str | None = Query(None, description="Filter by engine"),
    limit: int = Query(
        500, ge=1, le=5000, description="Maximum number of sessions to return"
    ),
) -> dict:
    """Lists session summaries across all engines for a project.

    Args:
        project: Optional project directory path filter. Omit to search
            across every project the user has session history for.
        engine: Optional engine filter ("claude", "codex", "opencode", "codebuddy").
        limit: Maximum number of sessions to return.

    Returns:
        dict: {"sessions": [...], "count": N}
    """
    sessions = (await asyncio.to_thread(find_all_sessions, project, engine=engine))[
        :limit
    ]
    return {
        "sessions": [wire(SessionSummary(**s.to_summary_dict())) for s in sessions],
        "count": len(sessions),
    }


@router.get("/history/audit")
async def get_audit_events(
    engine: str | None = Query(None, description="Filter by engine"),
    project: str | None = Query(
        None,
        description="Filter by project directory path; omit to search all projects",
    ),
    since: str | None = Query(None, description="ISO 8601 lower bound (inclusive)"),
    until: str | None = Query(None, description="ISO 8601 upper bound (inclusive)"),
    limit: int = Query(
        500, ge=1, le=5000, description="Maximum number of events to return"
    ),
) -> dict:
    """Returns a flattened, time-sorted message/tool-call event timeline.

    This is a message/tool-call history across engines and sessions — it is
    NOT an approval or permission log; no such data exists in the underlying
    session parsers.

    Args:
        engine: Optional engine filter ("claude", "codex", "opencode", "codebuddy").
        project: Optional project directory path filter. Omit to search
            across every project the user has session history for.
        since: Optional ISO 8601 lower bound on event timestamp (inclusive).
        until: Optional ISO 8601 upper bound on event timestamp (inclusive).
        limit: Maximum number of events to return after filtering.

    Returns:
        dict: {"events": [...], "count": N}
    """
    sessions = await asyncio.to_thread(find_all_sessions, project, engine=engine)
    events = build_audit_events(sessions)

    if since:
        since_dt = _parse_ts(since)
        events = [e for e in events if _parse_ts(e["timestamp"]) >= since_dt]
    if until:
        until_dt = _parse_ts(until)
        events = [e for e in events if _parse_ts(e["timestamp"]) <= until_dt]

    events = events[:limit]

    return {
        "events": [wire(AuditEvent(**event), drop_none=True) for event in events],
        "count": len(events),
    }


@router.get("/history/{engine}/{session_id}")
async def get_session_detail(
    engine: str,
    session_id: str,
    project: str = Query(..., description="Project directory path"),
) -> dict:
    """Gets the full detail of a specific session including all messages.

    Args:
        engine: The engine type.
        session_id: The session ID.
        project: The project directory path.

    Returns:
        dict: Full session data with messages, or 404 if not found.
    """
    session = await asyncio.to_thread(find_session_by_id, session_id, engine, project)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Session not found",
                "sessionId": session_id,
                "engine": engine,
            },
        )
    return wire(SessionDetail(**session.to_full_dict()))


@router.post("/history/convert")
async def convert_session(req: ConvertRequest) -> dict:
    """Converts a session from one engine format to another.

    Reads the source session, converts it to the target engine's native
    format, and writes it to the target engine's session storage directory.

    Args:
        req: The conversion request.

    Returns:
        dict: {"status": "ok", "newSessionId": "...", "targetEngine": "..."}
    """
    validated_project = _resolve_history_workspace(req.project_path)
    # Import here to avoid circular dependencies and only load when needed
    from core.session_history.writers import write_session

    session = await asyncio.to_thread(
        find_session_by_id, req.session_id, req.source_engine, validated_project
    )
    if not session:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Source session not found",
                "sessionId": req.session_id,
            },
        )

    try:
        new_id = await asyncio.to_thread(write_session, session, req.target_engine)
        return wire(
            ConvertResponse(
                status="ok",
                new_session_id=new_id,
                target_engine=req.target_engine,
                message=f"Session converted to {req.target_engine}. Use '{req.target_engine} continue' or equivalent to resume.",
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


def _resolve_history_workspace(project_path: str) -> str:
    """Validate *project_path* is a registered workspace, else raise 400/500."""
    from fastapi import HTTPException

    try:
        ws = resolve_registered_workspace(
            ConfigService(get_config_path()), project_path, interactive=True
        )
        return ws.path
    except WorkspaceConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except WorkspaceResolutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/history/convert-and-launch")
async def convert_and_launch(req: ConvertRequest) -> dict:
    """Converts a session and launches the target engine.

    Args:
        req: The conversion + launch request.

    Returns:
        dict: Launch result with converted session info.
    """
    validated_project = _resolve_history_workspace(req.project_path)
    from core.session_history.writers import write_session

    session = await asyncio.to_thread(
        find_session_by_id, req.session_id, req.source_engine, validated_project
    )
    if not session:
        raise HTTPException(
            status_code=404, detail={"error": "Source session not found"}
        )

    try:
        new_id = await asyncio.to_thread(write_session, session, req.target_engine)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"error": f"Conversion failed: {e}"}
        ) from e

    # Validates the argv is buildable (known engine, well-formed id) before
    # telling the caller to open a terminal on it.
    try:
        resume_command(req.target_engine, new_id, Path(validated_project))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return wire(
        ConvertAndLaunchResponse(
            status="ready",
            new_session_id=new_id,
            target_engine=req.target_engine,
            engine=req.target_engine,
            session_id=new_id,
            project=validated_project,
        )
    )


@router.post("/history/{engine}/{session_id}/continue")
async def continue_session(
    engine: str,
    session_id: str,
    project: str = Query(..., description="Project directory path"),
) -> dict:
    """Reports how to resume a session in the browser terminal.

    Nothing is converted — the already-native session is handed straight back
    to its engine CLI (``opencode -s``, ``claude --resume``, ``codex
    resume``...) with no CodeAgent prompt/skill injection.

    This used to open a GUI terminal window on whatever machine was running
    the server, which is useless the moment the browser is somewhere else
    (remote, container, headless) and returned 503 there. The engine now runs
    in the PTY the page already has: this endpoint validates and answers with
    what ``/api/pty/ws`` needs, and the websocket spawns it.

    Args:
        engine: The engine that owns *session_id*.
        session_id: The session ID to resume.
        project: The project directory path the session belongs to.

    Returns:
        dict: The engine, session id and project to attach a browser PTY to.
    """
    validated_project = _resolve_history_workspace(project)
    if engine not in ENGINES:
        raise HTTPException(status_code=400, detail=f"Unknown engine: {engine}")

    session = await asyncio.to_thread(
        find_session_by_id, session_id, engine, validated_project
    )
    if not session:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Session not found",
                "sessionId": session_id,
                "engine": engine,
            },
        )

    try:
        resume_command(engine, session_id, Path(validated_project))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return wire(
        ResumeTarget(
            status="ready",
            engine=engine,
            session_id=session_id,
            project=validated_project,
        )
    )


@router.delete("/history/{engine}/{session_id}")
async def delete_session(
    engine: str,
    session_id: str,
    project: str = Query(..., description="Project directory path"),
) -> dict:
    """Deletes a specific session from local history storage."""
    import sqlite3

    session = await asyncio.to_thread(find_session_by_id, session_id, engine, project)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Session not found",
                "sessionId": session_id,
                "engine": engine,
            },
        )

    validated_path = _validate_source_file_path(session.source_file or "", engine)

    if engine == "opencode":
        con = None
        try:
            con = sqlite3.connect(str(validated_path))
            with con:
                con.execute("DELETE FROM part WHERE session_id = ?", (session_id,))
                con.execute("DELETE FROM message WHERE session_id = ?", (session_id,))
                con.execute("DELETE FROM session WHERE id = ?", (session_id,))
        except sqlite3.Error as e:
            raise HTTPException(
                status_code=500, detail={"error": f"Failed to delete session row: {e}"}
            ) from e
        finally:
            if con is not None:
                con.close()
    else:
        try:
            validated_path.unlink()
        except OSError as e:
            raise HTTPException(
                status_code=500, detail={"error": f"Failed to delete session file: {e}"}
            ) from e

    return wire(DeleteSessionResponse(status="deleted", session_id=session_id))
