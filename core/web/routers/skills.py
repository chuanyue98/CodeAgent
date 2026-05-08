import os
from fastapi import APIRouter
from pathlib import Path
from core.services.skill_service import SkillService

router = APIRouter(prefix="/api")


def get_skills_root():
    env_path = os.environ.get("CA_SKILLS_ROOT")
    if env_path:
        return Path(env_path)
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    return root_dir / "skills"


@router.get("/skills")
async def list_skills():
    service = SkillService(get_skills_root())
    return service.get_detailed_skills()
