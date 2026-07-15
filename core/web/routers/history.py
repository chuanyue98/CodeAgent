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
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.session_history.audit import build_audit_events
from core.session_history.session_finder import (
    find_all_sessions,
    find_session_by_id,
)

router = APIRouter(prefix="/api")


def _parse_ts(ts: str) -> datetime:
    """Parse ISO 8601 timestamp string to a UTC-aware datetime for comparison."""
    try:
        normalized = ts.replace("Z", "+00:00") if ts else ""
        dt = datetime.fromisoformat(normalized) if normalized else datetime.min
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


class ConvertRequest(BaseModel):
    """Request body for cross-engine session conversion."""

    source_engine: str
    session_id: str
    target_engine: str
    project_path: str


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
    session = find_session_by_id(session_id, engine, project)
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

    session = find_session_by_id(req.session_id, req.source_engine, req.project_path)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Source session not found",
                "session_id": req.session_id,
            },
        )

    try:
        new_id = write_session(session, req.target_engine)
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

    session = find_session_by_id(req.session_id, req.source_engine, req.project_path)
    if not session:
        raise HTTPException(
            status_code=404, detail={"error": "Source session not found"}
        )

    try:
        new_id = write_session(session, req.target_engine)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail={"error": f"Conversion failed: {e}"}
        ) from e

    # Launch the engine in a visible terminal (same mechanism as /api/launch).
    import sys
    from pathlib import Path
    from core.web.routers.launch import launch_in_terminal

    _CA_LAUNCHER = Path(__file__).resolve().parents[3] / "ca_launcher.py"
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
    from pathlib import Path

    session = find_session_by_id(session_id, engine, project)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Session not found",
                "session_id": session_id,
                "engine": engine,
            },
        )

    if engine == "opencode":
        if not session.source_file:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Session source file path is empty",
                    "session_id": session_id,
                },
            )
        db_path = Path(session.source_file)
        if not db_path.exists() or not db_path.is_file():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"Session source file path is invalid: {session.source_file}",
                    "session_id": session_id,
                },
            )
        con = None
        try:
            con = sqlite3.connect(str(db_path))
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
        if not session.source_file:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Session source file path is empty",
                    "session_id": session_id,
                },
            )
        file_path = Path(session.source_file)
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"Session source file path is invalid: {session.source_file}",
                    "session_id": session_id,
                },
            )
        try:
            file_path.unlink()
        except OSError as e:
            raise HTTPException(
                status_code=500, detail={"error": f"Failed to delete session file: {e}"}
            ) from e

    return {"status": "deleted", "session_id": session_id}
