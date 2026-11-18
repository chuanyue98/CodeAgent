import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.resource_locator import get_default_config_path
from core.services.config_service import ConfigService

router = APIRouter(prefix="/api")


def get_config_path():
    return get_default_config_path()


def _resolve_config_path() -> Path:
    """优先使用测试在 ``server.CONFIG_PATH`` 上注入的路径，否则回退到默认配置路径。"""
    server_mod = sys.modules.get("core.web.server")
    override = getattr(server_mod, "CONFIG_PATH", None) if server_mod else None
    if override is not None:
        return Path(override)
    return get_config_path()


def _load_config(service: ConfigService) -> tuple[dict, list[str]]:
    """读取配置，返回 ``(config, warnings)``。"""
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
def list_projects():
    service = ConfigService(_resolve_config_path())
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
                "available": bool(path.strip()) and Path(path).expanduser().is_dir(),
            }
        )
    return result


@router.post("/projects")
def add_project(payload: ProjectPayload):
    try:
        service = ConfigService(_resolve_config_path())
        registry = service.add_project(payload.path, payload.group)
        return {"status": "success", "registry": registry}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/projects")
def delete_project(path: str):
    try:
        service = ConfigService(_resolve_config_path())
        registry = service.delete_project(path)
        return {"status": "success", "registry": registry}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/groups")
def list_groups():
    service = ConfigService(_resolve_config_path())
    config, _ = _load_config(service)
    return config.get("groups", {})


@router.post("/groups/{group_name}")
def update_group(group_name: str, definition: GroupDefinitionPayload):
    try:
        service = ConfigService(_resolve_config_path())
        group_data = definition.model_dump()

        def _modifier(config: dict) -> dict:
            groups = config.get("groups")
            if not isinstance(groups, dict):
                groups = {}
            groups[group_name] = group_data
            config["groups"] = groups
            return config

        service.modify_config(_modifier)
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
def delete_group(group_name: str):
    try:
        service = ConfigService(_resolve_config_path())
        remaining_groups: dict[str, Any] = {}

        def _modifier(config: dict) -> dict:
            nonlocal remaining_groups
            groups = config.get("groups")
            if not isinstance(groups, dict) or group_name not in groups:
                raise HTTPException(status_code=404, detail="Group not found")
            del groups[group_name]
            remaining_groups = dict(groups)
            return config

        service.modify_config(_modifier)
        return {"status": "success", "groups": remaining_groups}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config")
def get_config():
    path = _resolve_config_path()
    if not path.exists():
        return {"warnings": []}
    service = ConfigService(path)
    config, warnings = _load_config(service)
    if warnings:
        return {**config, "warnings": warnings}
    return config


@router.post("/config")
def update_config(config: ConfigPayload):
    try:
        config_dict = config.model_dump(exclude_none=True)
        # warnings 是服务端读取时附带的诊断字段，绝不持久化回 config.json。
        config_dict.pop("warnings", None)
        service = ConfigService(_resolve_config_path())
        service.update_config(config_dict)
        return {"status": "success", "message": "Configuration updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error writing config: {str(e)}"
        ) from e


@router.patch("/config")
def patch_config(patch: dict[str, Any]):
    try:
        service = ConfigService(_resolve_config_path())
        clean_patch = dict(patch)
        clean_patch.pop("warnings", None)

        def _apply(existing: dict) -> dict:
            merged = dict(existing)
            merged.update(clean_patch)
            merged.pop("warnings", None)
            return merged

        service.modify_config(_apply)
        return {"status": "success", "message": "Configuration patched"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error patching config: {str(e)}"
        ) from e
