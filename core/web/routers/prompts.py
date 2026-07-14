"""Prompts listing endpoint."""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.services.prompt_service import PromptService
from core.web.resource_paths import ROOT_DIR, resolve_resource_path

router = APIRouter(prefix="/api")


def get_prompts_root():
    return resolve_resource_path("prompt", "CA_PROMPTS_ROOT")


def get_root_dir():
    env_path = os.environ.get("CA_ROOT_DIR")
    if env_path:
        return Path(env_path)
    return ROOT_DIR


@router.get("/prompts")
async def list_prompts() -> list:
    """List all prompt groups with metadata."""
    try:
        service = PromptService(get_prompts_root(), get_root_dir())
        return service.get_prompt_groups()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
