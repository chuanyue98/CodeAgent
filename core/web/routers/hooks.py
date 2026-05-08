import os
from fastapi import APIRouter
from pathlib import Path
from core.services.hook_service import HookService
from core.web.resource_paths import resolve_resource_path, ROOT_DIR

router = APIRouter(prefix="/api")


def get_hooks_root():
    return resolve_resource_path("hooks", "CA_HOOKS_ROOT")


def get_config_path():
    env_path = os.environ.get("CA_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    return ROOT_DIR / "config.json"


@router.get("/hooks")
async def list_hooks():
    service = HookService(get_hooks_root(), get_config_path())
    return service.get_detailed_hooks()
