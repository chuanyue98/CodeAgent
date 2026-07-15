from __future__ import annotations

from core import doctor


def test_check_python_statuses():
    section_ok = doctor.Section("Python")
    doctor.check_python(section_ok)
    assert section_ok.checks[0].status in (doctor.OK, doctor.WARN, doctor.FAIL)


def test_check_config_valid(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"groups": {}}')
    section = doctor.Section("Config")
    cfg = doctor.check_config(section, tmp_path)
    assert cfg is not None
    assert section.checks[0].status == doctor.OK


def test_check_config_missing(tmp_path):
    section = doctor.Section("Config")
    cfg = doctor.check_config(section, tmp_path)
    assert cfg is None
    assert any(c.status == doctor.FAIL for c in section.checks)


def test_check_directories_present(tmp_path):
    (tmp_path / "prompt").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "hooks").mkdir()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "tasks").mkdir()
    section = doctor.Section("Dirs")
    doctor.check_directories(section, tmp_path)
    assert all(c.status == doctor.OK for c in section.checks)


def test_check_directories_missing(tmp_path):
    section = doctor.Section("Dirs")
    doctor.check_directories(section, tmp_path)
    assert all(c.status == doctor.WARN for c in section.checks)


def test_check_stale_injections_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    section = doctor.Section("Stale")
    stale = doctor.check_stale_injections(section)
    assert stale == []
    assert section.checks[0].status == doctor.OK


def test_check_stale_injections_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    claude_settings = tmp_path / ".claude" / "settings.json"
    claude_settings.parent.mkdir(parents=True)
    claude_settings.write_text('{"_ca_injected": true}')
    section = doctor.Section("Stale")
    stale = doctor.check_stale_injections(section)
    assert len(stale) == 1
    assert section.checks[0].status == doctor.WARN


def test_get_doctor_sections_returns_sections():
    sections = doctor.get_doctor_sections(fix=False)
    assert len(sections) > 0
    assert all(isinstance(s, doctor.Section) for s in sections)
