from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.services.config_service import ConfigService
from core.resource_locator import get_default_config_path

router = APIRouter(prefix="/api")


def get_config_path():
    return get_default_config_path()


def _load_config(service: ConfigService) -> tuple[dict, list[str]]:
    """Load config, returning (config, warnings) without raising on warnings."""
    return service.get_config()


# ── Pydantic request models ──────────────────────────────────────────────────


class ProjectPayload(BaseModel):
    path: str = Field(min_length=1)
    group: str = Field(min_length=1)

    @field_validator("path", "group")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class ProxyPayload(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(gt=0, le=65535)


class GroupDefinitionPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    skills: list[str] = Field(default_factory=list)
    prompts: list[str] = Field(default_factory=list)
    hooks: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)


class ConfigPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    default_mode: str | None = None
    language: str | None = None
    groups: dict[str, GroupDefinitionPayload] | None = None
    project_registry: list[ProjectPayload] | None = None


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/projects")
async def list_projects():
    service = ConfigService(get_config_path())
    config, _ = _load_config(service)
    projects = config.get("project_registry", [])
    result = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        path = project.get("path")
        group = project.get("group")
        if not isinstance(path, str) or not isinstance(group, str):
            continue
        if not path.strip() or not group.strip():
            continue
        result.append(
            {
                "path": path,
                "group": group,
                "available": bool(path.strip())
                and Path(path).expanduser().is_dir(),
            }
        )
    return result


@router.post("/projects")
async def add_project(payload: ProjectPayload):
    try:
        service = ConfigService(get_config_path())
        registry = service.add_project(payload.path, payload.group)
        return {"status": "success", "registry": registry}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/projects")
async def delete_project(path: str):
    try:
        service = ConfigService(get_config_path())
        registry = service.delete_project(path)
        return {"status": "success", "registry": registry}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/groups")
async def list_groups():
    service = ConfigService(get_config_path())
    config, _ = _load_config(service)
    return config.get("groups", {})


@router.post("/groups/{group_name}")
async def update_group(group_name: str, definition: GroupDefinitionPayload):
    try:
        service = ConfigService(get_config_path())
        config, _ = _load_config(service)
        if "groups" not in config:
            config["groups"] = {}
        group_data = definition.model_dump()
        config["groups"][group_name] = group_data
        service.update_config(config)
        return {
            "status": "success",
            "group": group_name,
            "definition": group_data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/groups/{group_name}")
async def delete_group(group_name: str):
    try:
        service = ConfigService(get_config_path())
        config, _ = _load_config(service)
        if "groups" in config and group_name in config["groups"]:
            del config["groups"][group_name]
        else:
            raise HTTPException(status_code=404, detail="Group not found")
        service.update_config(config)
        return {"status": "success", "groups": config.get("groups", {})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config")
async def get_config():
    path = get_config_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="config.json not found")
    service = ConfigService(path)
    config, warnings = _load_config(service)
    if warnings:
        return {**config, "warnings": warnings}
    return config


@router.post("/config")
async def update_config(config: ConfigPayload):
    try:
        config_dict = config.model_dump(exclude_none=True)
        service = ConfigService(get_config_path())
        service.update_config(config_dict)
        return {"status": "success", "message": "Configuration updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error writing config: {str(e)}"
        ) from e
