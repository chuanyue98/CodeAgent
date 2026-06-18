import json
from core.services.config_service import ConfigService


def test_config_service_crud(tmp_path):
    config_path = tmp_path / "config.json"
    service = ConfigService(config_path)

    # Get empty
    assert service.get_config() == ({}, [])

    # Update
    service.update_config({"test": "val"})
    assert service.get_config() == ({"test": "val"}, [])
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"test": "val"}


def test_config_service_malformed_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{ malformed json }", encoding="utf-8")
    service = ConfigService(config_path)

    data, warnings = service.get_config()
    assert data == {}
    assert len(warnings) > 0
    assert "Failed to parse config.json" in warnings[0]

    try:
        service.update_config({"replacement": True})
    except ValueError as exc:
        assert "Refusing to overwrite malformed configuration" in str(exc)
    else:
        raise AssertionError("Malformed configuration should not be overwritten")


def test_config_service_utf8_bom(tmp_path):
    config_path = tmp_path / "config.json"
    # Write UTF-8 BOM followed by JSON
    content = '{"test": "bom"}'.encode("utf-8-sig")
    config_path.write_bytes(content)

    service = ConfigService(config_path)
    data, warnings = service.get_config()

    assert data == {"test": "bom"}
    assert warnings == []


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
