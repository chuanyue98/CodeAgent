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

from fastapi import APIRouter, Query
from pydantic import BaseModel

from core.session_history.audit import build_audit_events
from core.session_history.session_finder import (
    find_all_sessions,
    find_session_by_id,
)

router = APIRouter(prefix="/api")


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
        events = [e for e in events if e["timestamp"] >= since]
    if until:
        events = [e for e in events if e["timestamp"] <= until]

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
        return {
            "error": "Session not found",
            "session_id": session_id,
            "engine": engine,
        }
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
        return {"error": "Source session not found", "session_id": req.session_id}

    try:
        new_id = write_session(session, req.target_engine)
        return {
            "status": "ok",
            "new_session_id": new_id,
            "target_engine": req.target_engine,
            "message": f"Session converted to {req.target_engine}. Use '{req.target_engine} continue' or equivalent to resume.",
        }
    except Exception as e:
        return {"error": str(e)}


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
        return {"error": "Source session not found"}

    try:
        new_id = write_session(session, req.target_engine)
    except Exception as e:
        return {"error": f"Conversion failed: {e}"}

    # Launch the engine in a terminal (same mechanism as /api/launch)
    import shlex
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    _CA_LAUNCHER = Path(__file__).resolve().parents[3] / "ca_launcher.py"
    cmd = [sys.executable, str(_CA_LAUNCHER), req.target_engine]

    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "start", "cmd", "/k"] + cmd)
    elif sys.platform == "darwin":
        script = f'tell app "Terminal" to do script "cd {shlex.quote(Path.cwd().as_posix())} && {shlex.join(cmd)}"'
        subprocess.Popen(["osascript", "-e", script])
    else:
        for terminal in ["gnome-terminal", "konsole", "xterm"]:
            if shutil.which(terminal):
                args = (
                    [terminal, "--"]
                    if terminal == "gnome-terminal"
                    else [terminal, "-e"]
                )
                subprocess.Popen(args + cmd)
                break

    return {
        "status": "launched",
        "new_session_id": new_id,
        "target_engine": req.target_engine,
    }
