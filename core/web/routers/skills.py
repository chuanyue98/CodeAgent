"""Skills listing endpoint."""

from fastapi import APIRouter, HTTPException

from core.services.skill_service import SkillService
from core.web.resource_paths import resolve_resource_path

router = APIRouter(prefix="/api")


def get_skills_root():
    return resolve_resource_path("skills", "CA_SKILLS_ROOT")


@router.get("/skills")
async def list_skills() -> dict:
    """List all registered skills with metadata."""
    try:
        service = SkillService(get_skills_root())
        return service.get_detailed_skills()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
