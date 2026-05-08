import json
from core.services.config_service import ConfigService


def test_config_service_crud(tmp_path):
    config_path = tmp_path / "config.json"
    service = ConfigService(config_path)

    # Get empty
    assert service.get_config() == {}

    # Update
    service.update_config({"test": "val"})
    assert service.get_config() == {"test": "val"}
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"test": "val"}


def test_config_service_project_management(tmp_path):
    config_path = tmp_path / "config.json"
    service = ConfigService(config_path)

    # Add
    registry = service.add_project("/path/1", "group1")
    assert any(p["path"] == "/path/1" for p in registry)

    # Update
    registry = service.add_project("/path/1", "group2")
    assert any(p["path"] == "/path/1" and p["group"] == "group2" for p in registry)

    # Delete
    registry = service.delete_project("/path/1")
    assert not any(p["path"] == "/path/1" for p in registry)
