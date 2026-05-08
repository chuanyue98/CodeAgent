from fastapi import APIRouter
from core.services.skill_service import SkillService
from core.web.resource_paths import resolve_resource_path

router = APIRouter(prefix="/api")


def get_skills_root():
    return resolve_resource_path("skills", "CA_SKILLS_ROOT")


@router.get("/skills")
async def list_skills():
    service = SkillService(get_skills_root())
    return service.get_detailed_skills()
