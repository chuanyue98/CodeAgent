import os
from fastapi import APIRouter
from pathlib import Path
from core.services.prompt_service import PromptService
from core.web.resource_paths import resolve_resource_path, ROOT_DIR

router = APIRouter(prefix="/api")


def get_prompts_root():
    return resolve_resource_path("prompt", "CA_PROMPTS_ROOT")


def get_root_dir():
    env_path = os.environ.get("CA_ROOT_DIR")
    if env_path:
        return Path(env_path)
    return ROOT_DIR


@router.get("/prompts")
async def list_prompts():
    service = PromptService(get_prompts_root(), get_root_dir())
    return service.get_prompt_groups()
