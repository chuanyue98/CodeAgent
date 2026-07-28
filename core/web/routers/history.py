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
from pydantic import BaseModel, field_validator

from core.constants import ENGINES
from core.session_history.audit import build_audit_events
from core.session_history.session_finder import (
    find_all_sessions,
    find_session_by_id,
)

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
    elif engine == "gemini":
        allowed_dirs.append((home / ".gemini" / "tmp").resolve())
    elif engine == "opencode":
        allowed_dirs.append((home / ".opencode").resolve())
        allowed_dirs.append((home / ".local" / "share" / "opencode").resolve())

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


class ConvertRequest(BaseModel):
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
        engine: Optional engine filter ("claude", "codex", "gemini", "opencode").
        limit: Maximum number of sessions to return.

    Returns:
        dict: {"sessions": [...], "count": N}
    """
    sessions = (await asyncio.to_thread(find_all_sessions, project, engine=engine))[
        :limit
    ]
    return {
        "sessions": [s.to_summary_dict() for s in sessions],
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
        engine: Optional engine filter ("claude", "codex", "gemini", "opencode").
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

    return {"events": events, "count": len(events)}


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
                "session_id": session_id,
                "engine": engine,
            },
        )
    return session.to_full_dict()


@router.post("/history/convert")
async def convert_session(req: ConvertRequest) -> dict:
    """Converts a session from one engine format to another.

    Reads the source session, converts it to the target engine's native
    format, and writes it to the target engine's session storage directory.

    Args:
        req: The conversion request.

    Returns:
        dict: {"status": "ok", "new_session_id": "...", "target_engine": "..."}
    """
    # Import here to avoid circular dependencies and only load when needed
    from core.session_history.writers import write_session

    session = await asyncio.to_thread(
        find_session_by_id, req.session_id, req.source_engine, req.project_path
    )
    if not session:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Source session not found",
                "session_id": req.session_id,
            },
        )

    try:
        new_id = await asyncio.to_thread(write_session, session, req.target_engine)
        return {
            "status": "ok",
            "new_session_id": new_id,
            "target_engine": req.target_engine,
            "message": f"Session converted to {req.target_engine}. Use '{req.target_engine} continue' or equivalent to resume.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.post("/history/convert-and-launch")
async def convert_and_launch(req: ConvertRequest) -> dict:
    """Converts a session and launches the target engine.

    Args:
        req: The conversion + launch request.

    Returns:
        dict: Launch result with converted session info.
    """
    from core.session_history.writers import write_session

    session = await asyncio.to_thread(
        find_session_by_id, req.session_id, req.source_engine, req.project_path
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

    # Launch the engine in a visible terminal (same mechanism as /api/launch).
    import sys

    from core.web.routers.launch import _CA_LAUNCHER, launch_in_terminal

    cmd = [sys.executable, str(_CA_LAUNCHER), req.target_engine]

    try:
        terminal = launch_in_terminal(cmd, cwd=Path(req.project_path))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to open terminal: {exc}"
        ) from exc

    return {
        "status": "launched",
        "new_session_id": new_id,
        "target_engine": req.target_engine,
        "terminal": terminal,
    }


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
                "session_id": session_id,
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

    return {"status": "deleted", "session_id": session_id}
