import os
from fastapi import APIRouter
from pathlib import Path
from core.services.prompt_service import PromptService

router = APIRouter(prefix="/api")


def get_prompts_root():
    env_path = os.environ.get("CA_PROMPTS_ROOT")
    if env_path:
        return Path(env_path)
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    return root_dir / "prompt"


def get_root_dir():
    env_path = os.environ.get("CA_ROOT_DIR")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parent.parent.parent.parent


@router.get("/prompts")
async def list_prompts():
    service = PromptService(get_prompts_root(), get_root_dir())
    return service.get_prompt_groups()
