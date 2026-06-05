import os
from fastapi import APIRouter, Body, HTTPException
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from core.services.config_service import ConfigService

router = APIRouter(prefix="/api")


class ProjectPayload(BaseModel):
    path: str = Field(min_length=1)
    group: str = Field(min_length=1)


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
    default_group: str | None = None
    language: str | None = None
    proxy: ProxyPayload | list[ProxyPayload] | None = None
    paths: dict[str, str] | None = None
    project_registry: list[ProjectPayload] | None = None
    groups: dict[str, GroupDefinitionPayload] | None = None


def get_config_path():
    # Use environment variable if set (for tests), otherwise default to ROOT_DIR
    env_path = os.environ.get("CA_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    return root_dir / "config.json"


@router.get("/projects")
async def list_projects():
    service = ConfigService(get_config_path())
    config, _ = service.get_config()
    return config.get("project_registry", [])


@router.post("/projects")
async def add_project(project: ProjectPayload):
    try:
        service = ConfigService(get_config_path())
        registry = service.add_project(project.path, project.group)
        return {"status": "success", "registry": registry}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects")
async def delete_project(path: str):
    try:
        service = ConfigService(get_config_path())
        registry = service.delete_project(path)
        return {"status": "success", "registry": registry}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/groups")
async def list_groups():
    service = ConfigService(get_config_path())
    config, _ = service.get_config()
    return config.get("groups", {})


@router.post("/groups/{group_name}")
async def update_group(group_name: str, definition: GroupDefinitionPayload):
    try:
        service = ConfigService(get_config_path())
        config, _ = service.get_config()
        if "groups" not in config:
            config["groups"] = {}
        config["groups"][group_name] = definition.model_dump()
        service.update_config(config)
        return {
            "status": "success",
            "group": group_name,
            "definition": config["groups"][group_name],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/groups/{group_name}")
async def delete_group(group_name: str):
    service = ConfigService(get_config_path())
    config, _ = service.get_config()
    groups = config.get("groups", {})
    if group_name not in groups:
        raise HTTPException(status_code=404, detail="Group not found")

    try:
        del groups[group_name]
        config["groups"] = groups
        service.update_config(config)
        return {"status": "success", "groups": config.get("groups", {})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_config():
    path = get_config_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="config.json not found")
    service = ConfigService(path)
    config, _ = service.get_config()
    return config


@router.post("/config")
async def update_config(config: ConfigPayload = Body(...)):
    try:
        service = ConfigService(get_config_path())
        service.update_config(config.model_dump(exclude_none=True))
        return {"status": "success", "message": "Configuration updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error writing config: {str(e)}")
