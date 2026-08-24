"""Web API router for MCP server management, per engine.

Endpoints:
  POST   /api/mcp/sync                            Copy servers between engines.
  GET    /api/mcp/{engine}?project=<path>        List configured MCP servers.
  POST   /api/mcp/{engine}                        Add an MCP server.
  DELETE /api/mcp/{engine}/{name}?project=<path>  Remove an MCP server.

``/sync`` is declared before the ``/{engine}`` routes so the literal path
wins the match rather than being read as an engine name.

Mutations shell out to each engine's own ``mcp`` CLI subcommand (or, for
opencode where the spike found that absent, edit the native
config file directly) — see core/services/mcp_service.py and
docs/mcp-cli-spike-results.md for the full rationale. codex and opencode
are global-scoped (not per-project) in this CLI version; the ``project``
query param is accepted for all four engines for a uniform API but is only
load-bearing for claude.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from core.services import mcp_service
from core.web.case_convert import ProtocolModel, wire

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class AddMcpServerRequest(ProtocolModel):
    """Request body for adding an MCP server."""

    project: str
    name: str
    command: list[str] | None = None
    url: str | None = None
    env: dict[str, str] | None = None
    transport: str | None = None


class McpServerEntry(ProtocolModel):
    """One configured MCP server, normalized across engines."""

    name: str
    scope: str
    transport: str
    command: list[str] | None = None
    url: str | None = None
    env: dict[str, str] = {}


class SyncMcpRequest(ProtocolModel):
    """Request body for syncing MCP servers from one engine to others."""

    project: str
    source: str
    targets: list[str] | None = None
    names: list[str] | None = None
    overwrite: bool = False
    dry_run: bool = False


class SyncMcpResult(ProtocolModel):
    """Outcome of syncing one server into one target engine."""

    engine: str
    name: str
    action: str
    detail: str


@router.post("/sync")
def sync_mcp_servers(req: SyncMcpRequest) -> list[dict]:
    """Copies MCP servers from one engine's config into the others'.

    Individual failures are reported as ``failed`` records rather than raised,
    so a partial sync stays visible; only a bad request (unknown engine,
    unknown server name) is rejected outright.
    """
    try:
        results = mcp_service.sync_servers(
            req.source,
            req.project,
            targets=req.targets,
            names=req.names,
            overwrite=req.overwrite,
            dry_run=req.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [wire(SyncMcpResult(**result)) for result in results]


@router.get("/{engine}")
def list_mcp_servers(
    engine: str,
    project: str = Query(..., description="Project directory path"),
) -> list[dict]:
    """Lists configured MCP servers for one engine."""
    try:
        entries = mcp_service.list_servers(engine, project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [wire(McpServerEntry(**entry)) for entry in entries]


@router.post("/{engine}")
def add_mcp_server(engine: str, req: AddMcpServerRequest) -> dict:
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
def remove_mcp_server(
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
