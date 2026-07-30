from __future__ import annotations

from pathlib import Path

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


def test_check_stale_injections_detects_opencode_and_codex(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    opencode_settings = tmp_path / ".opencode" / "settings.json"
    opencode_settings.parent.mkdir(parents=True)
    opencode_settings.write_text('{"_ca_injected": true}')
    codex_settings = tmp_path / ".codex" / "settings.json"
    codex_settings.parent.mkdir(parents=True)
    codex_settings.write_text('{"_ca_injected": true}')

    section = doctor.Section("Stale")
    stale = doctor.check_stale_injections(section)

    assert set(stale) == {opencode_settings, codex_settings}
    assert section.checks[0].status == doctor.WARN


def test_get_doctor_sections_returns_sections():
    sections = doctor.get_doctor_sections(fix=False)
    assert len(sections) > 0
    assert all(isinstance(s, doctor.Section) for s in sections)


def test_preview_stale_injections_leaves_files_untouched(tmp_path, capsys):
    settings = tmp_path / "settings.json"
    settings.write_text('{"_ca_injected": true}')
    doctor.preview_stale_injections([settings])
    assert settings.exists()
    assert '{"_ca_injected": true}' == settings.read_text()
    assert "Would remove" in capsys.readouterr().out


def test_preview_stale_injections_reports_restore_when_backup_exists(tmp_path, capsys):
    settings = tmp_path / "settings.json"
    settings.write_text('{"_ca_injected": true}')
    backup = tmp_path / "settings.json.bak"
    backup.write_text('{"original": true}')
    doctor.preview_stale_injections([settings])
    assert settings.read_text() == '{"_ca_injected": true}'
    assert backup.exists()
    assert "Would restore" in capsys.readouterr().out


def test_dry_run_does_not_modify_stale_injections(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    claude_settings = tmp_path / ".claude" / "settings.json"
    claude_settings.parent.mkdir(parents=True)
    claude_settings.write_text('{"_ca_injected": true}')
    doctor.get_doctor_sections(fix=False, dry_run=True)
    assert claude_settings.exists()
    assert claude_settings.read_text() == '{"_ca_injected": true}'


def test_lightweight_resolver_uses_config_manager(tmp_path, monkeypatch):
    for directory in ("skills", "prompt", "hooks", "plugins"):
        (tmp_path / directory).mkdir()
    monkeypatch.chdir(tmp_path)

    resolver = doctor._LightweightResolver(
        tmp_path,
        {"groups": {"codeagent": {"skills": []}}, "default_group": "common"},
    )

    assert resolver.get_current_project_group() == "codeagent"
    assert resolver._get_skill_search_roots() == [(tmp_path / "skills").resolve()]
    assert resolver.get_skills_to_mount()[0] == []


# --- cross-engine parity checks -----------------------------------------


def _mcp_servers(mapping):
    """Builds a mcp_service.list_servers stand-in from {engine: [names]}."""

    def list_servers(engine, project_path):
        return [{"name": n} for n in mapping.get(engine, [])]

    return list_servers


def test_mcp_drift_reports_nothing_when_no_servers_anywhere(monkeypatch):
    from core.services import mcp_service

    monkeypatch.setattr(mcp_service, "list_servers", _mcp_servers({}))
    section = doctor.Section("Parity")

    doctor.check_mcp_drift(section)

    assert section.checks[0].status == doctor.INFO
    assert "none configured" in section.checks[0].detail


def test_mcp_drift_is_ok_when_all_engines_match(monkeypatch):
    from core.services import mcp_service

    monkeypatch.setattr(
        mcp_service,
        "list_servers",
        _mcp_servers(dict.fromkeys(("claude", "codex", "gemini", "opencode"), ["fs"])),
    )
    section = doctor.Section("Parity")

    doctor.check_mcp_drift(section)

    assert section.checks[0].status == doctor.OK


def test_mcp_drift_names_the_engines_a_server_is_on(monkeypatch):
    from core.services import mcp_service

    monkeypatch.setattr(
        mcp_service,
        "list_servers",
        _mcp_servers({"claude": ["fs"], "codex": [], "gemini": [], "opencode": []}),
    )
    section = doctor.Section("Parity")

    doctor.check_mcp_drift(section)

    check = section.checks[0]
    assert check.status == doctor.WARN
    assert "fs" in check.detail
    assert "claude" in check.detail
    assert "ca mcp sync" in check.fix_hint


def test_mcp_drift_survives_an_unreadable_engine_config(monkeypatch):
    from core.services import mcp_service

    def boom(engine, project_path):
        raise RuntimeError("nope")

    monkeypatch.setattr(mcp_service, "list_servers", boom)
    section = doctor.Section("Parity")

    doctor.check_mcp_drift(section)

    assert section.checks[0].status == doctor.WARN
    assert "could not evaluate" in section.checks[0].detail


def test_hook_delivery_is_quiet_without_hooks(tmp_path, monkeypatch):
    monkeypatch.setattr(
        doctor._LightweightResolver, "get_hooks_to_inject", lambda self: ([], [])
    )
    section = doctor.Section("Parity")

    doctor.check_hook_delivery(section, tmp_path, {"groups": {}})

    assert section.checks[0].status == doctor.INFO
    assert "no hooks configured" in section.checks[0].detail


def test_hook_delivery_warns_when_codex_project_is_untrusted(tmp_path, monkeypatch):
    """A hook can resolve fine yet be silently ignored by codex."""
    monkeypatch.setattr(
        doctor._LightweightResolver,
        "get_hooks_to_inject",
        lambda self: ([{"name": "h", "event": "before_tool", "command": "c"}], []),
    )
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "config.toml").write_text('model = "x"\n', encoding="utf-8")
    monkeypatch.setattr(doctor.Path, "home", lambda: home)
    monkeypatch.chdir(tmp_path)
    section = doctor.Section("Parity")

    doctor.check_hook_delivery(section, tmp_path, {"groups": {}})

    codex_check = next(c for c in section.checks if "codex" in c.label)
    assert codex_check.status == doctor.WARN
    assert "trust_level" in codex_check.fix_hint


def test_hook_delivery_is_ok_when_codex_project_is_trusted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        doctor._LightweightResolver,
        "get_hooks_to_inject",
        lambda self: ([{"name": "h", "event": "before_tool", "command": "c"}], []),
    )
    monkeypatch.chdir(tmp_path)
    project = str(Path(tmp_path).resolve()).replace("\\", "\\\\")
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "config.toml").write_text(
        f'[projects."{project}"]\ntrust_level = "trusted"\n', encoding="utf-8"
    )
    monkeypatch.setattr(doctor.Path, "home", lambda: home)
    section = doctor.Section("Parity")

    doctor.check_hook_delivery(section, tmp_path, {"groups": {}})

    codex_check = next(c for c in section.checks if "codex" in c.label)
    assert codex_check.status == doctor.OK
