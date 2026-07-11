"""Web API router for MCP server management, per engine.

Endpoints:
  GET    /api/mcp/{engine}?project=<path>        List configured MCP servers.
  POST   /api/mcp/{engine}                        Add an MCP server.
  DELETE /api/mcp/{engine}/{name}?project=<path>  Remove an MCP server.

Mutations shell out to each engine's own ``mcp`` CLI subcommand (or, for
gemini/opencode where the spike found that broken/absent, edit the native
config file directly) — see core/services/mcp_service.py and
docs/mcp-cli-spike-results.md for the full rationale. codex and opencode
are global-scoped (not per-project) in this CLI version; the ``project``
query param is accepted for all four engines for a uniform API but is only
load-bearing for claude/gemini.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.services import mcp_service

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class AddMcpServerRequest(BaseModel):
    """Request body for adding an MCP server."""

    project: str
    name: str
    command: list[str] | None = None
    url: str | None = None
    env: dict[str, str] | None = None
    transport: str | None = None


@router.get("/{engine}")
async def list_mcp_servers(
    engine: str,
    project: str = Query(..., description="Project directory path"),
) -> list[dict]:
    """Lists configured MCP servers for one engine."""
    try:
        return mcp_service.list_servers(engine, project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{engine}")
async def add_mcp_server(engine: str, req: AddMcpServerRequest) -> dict:
    """Adds an MCP server via the engine's own CLI."""
    try:
        mcp_service.add_server(
            engine,
            req.project,
            req.name,
            command=req.command,
            url=req.url,
            env=req.env,
            transport=req.transport,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.delete("/{engine}/{name}")
async def remove_mcp_server(
    engine: str,
    name: str,
    project: str = Query(..., description="Project directory path"),
) -> dict:
    """Removes an MCP server."""
    try:
        mcp_service.remove_server(engine, project, name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok"}
