"""Hooks listing endpoint."""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.services.hook_service import HookService
from core.web.resource_paths import ROOT_DIR, resolve_resource_path

router = APIRouter(prefix="/api")


def get_hooks_root():
    return resolve_resource_path("hooks", "CA_HOOKS_ROOT")


def get_config_path():
    env_path = os.environ.get("CA_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    return ROOT_DIR / "config.json"


@router.get("/hooks")
async def list_hooks() -> list:
    """List all registered hooks with metadata."""
    try:
        service = HookService(get_hooks_root(), get_config_path())
        return service.get_detailed_hooks()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
