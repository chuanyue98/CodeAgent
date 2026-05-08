import os
from fastapi import APIRouter
from pathlib import Path
from core.services.plugin_service import PluginService

router = APIRouter(prefix="/api")


def get_plugins_root():
    env_path = os.environ.get("CA_PLUGINS_ROOT")
    if env_path:
        return Path(env_path)
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    return root_dir / "plugins"


@router.get("/plugins")
async def list_plugins():
    service = PluginService(get_plugins_root())
    return service.get_detailed_plugins()
