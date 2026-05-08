import os
from fastapi import APIRouter, Body, HTTPException
from pathlib import Path
from core.services.config_service import ConfigService

router = APIRouter(prefix="/api")


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
    return service.get_config().get("project_registry", [])


@router.post("/projects")
async def add_project(project: dict = Body(...)):
    if not project.get("path") or not project.get("group"):
        raise HTTPException(status_code=400, detail="Path and group are required")
    try:
        service = ConfigService(get_config_path())
        registry = service.add_project(project["path"], project["group"])
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
    return service.get_config().get("groups", {})


@router.post("/groups/{group_name}")
async def update_group(group_name: str, definition: dict = Body(...)):
    try:
        service = ConfigService(get_config_path())
        config = service.get_config()
        if "groups" not in config:
            config["groups"] = {}
        config["groups"][group_name] = definition
        service.update_config(config)
        return {"status": "success", "group": group_name, "definition": definition}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/groups/{group_name}")
async def delete_group(group_name: str):
    try:
        service = ConfigService(get_config_path())
        config = service.get_config()
        if "groups" in config and group_name in config["groups"]:
            del config["groups"][group_name]
        else:
            raise HTTPException(status_code=404, detail="Group not found")
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
    return service.get_config()


@router.post("/config")
async def update_config(config: dict = Body(...)):
    try:
        service = ConfigService(get_config_path())
        service.update_config(config)
        return {"status": "success", "message": "Configuration updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error writing config: {str(e)}")
