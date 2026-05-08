import os
from fastapi import APIRouter
from pathlib import Path
from core.services.hook_service import HookService

router = APIRouter(prefix="/api")


def get_hooks_root():
    env_path = os.environ.get("CA_HOOKS_ROOT")
    if env_path:
        return Path(env_path)
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    return root_dir / "hooks"


def get_config_path():
    env_path = os.environ.get("CA_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    return root_dir / "config.json"


@router.get("/hooks")
async def list_hooks():
    service = HookService(get_hooks_root(), get_config_path())
    return service.get_detailed_hooks()
