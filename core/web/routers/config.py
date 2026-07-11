import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.services.config_service import ConfigService

router = APIRouter(prefix="/api")


def get_config_path():
    # Use environment variable if set (for tests), otherwise default to ROOT_DIR
    env_path = os.environ.get("CA_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    return root_dir / "config.json"


def _load_config(service: ConfigService) -> dict:
    config, warnings = service.get_config()
    if warnings:
        raise HTTPException(status_code=500, detail=warnings[0])
    return config


# ── Pydantic request models ──────────────────────────────────────────────────


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
    language: str | None = None
    proxy: ProxyPayload | None = None
    groups: dict[str, GroupDefinitionPayload] | None = None
    project_registry: list[dict] | None = None


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/projects")
async def list_projects():
    service = ConfigService(get_config_path())
    config = _load_config(service)
    return config.get("project_registry", [])


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
    config = _load_config(service)
    return config.get("groups", {})


@router.post("/groups/{group_name}")
async def update_group(group_name: str, definition: GroupDefinitionPayload):
    try:
        service = ConfigService(get_config_path())
        config = _load_config(service)
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
        config = _load_config(service)
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
    return _load_config(service)


@router.post("/config")
async def update_config(config: dict):
    try:
        service = ConfigService(get_config_path())
        service.update_config(config)
        return {"status": "success", "message": "Configuration updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error writing config: {str(e)}"
        ) from e
