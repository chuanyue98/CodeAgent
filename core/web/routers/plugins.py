"""Plugins listing endpoint."""

from fastapi import APIRouter, HTTPException

from core.services.plugin_service import PluginService
from core.web.resource_paths import resolve_resource_path

router = APIRouter(prefix="/api")


def get_plugins_root():
    return resolve_resource_path("plugins", "CA_PLUGINS_ROOT")


@router.get("/plugins")
async def list_plugins() -> dict:
    """List all registered plugins with metadata."""
    try:
        service = PluginService(get_plugins_root())
        return service.get_detailed_plugins()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
