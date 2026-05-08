from fastapi import APIRouter
from core.services.plugin_service import PluginService
from core.web.resource_paths import resolve_resource_path

router = APIRouter(prefix="/api")


def get_plugins_root():
    return resolve_resource_path("plugins", "CA_PLUGINS_ROOT")


@router.get("/plugins")
async def list_plugins():
    service = PluginService(get_plugins_root())
    return service.get_detailed_plugins()
