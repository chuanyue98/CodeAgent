from __future__ import annotations

from pathlib import Path

import pytest

from core import doctor, i18n, resource_locator


@pytest.fixture(autouse=True)
def _english_output():
    """Doctor output is translated, so pin a language before asserting on it.

    Without this the assertions below would pass or fail depending on the
    developer's OS locale.
    """
    i18n.set_language("en")
    yield
    i18n.set_language(None)


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


def test_check_stale_injections_detects_codex_config_toml(tmp_path, monkeypatch):
    """Codex hooks live in config.toml; a SIGKILLed run leaves the marker there.

    The old json.load-based check silently skipped TOML, so this residue was
    invisible to `ca doctor` forever.
    """
    monkeypatch.chdir(tmp_path)
    codex_config = tmp_path / ".codex" / "config.toml"
    codex_config.parent.mkdir(parents=True)
    codex_config.write_text(
        'model = "gpt-5"\n\n_ca_injected = true\n\n[hooks]\n',
        encoding="utf-8",
    )

    section = doctor.Section("Stale")
    stale = doctor.check_stale_injections(section)

    assert stale == [codex_config]
    assert section.checks[0].status == doctor.WARN


def test_check_stale_injections_ignores_clean_codex_config_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    codex_config = tmp_path / ".codex" / "config.toml"
    codex_config.parent.mkdir(parents=True)
    codex_config.write_text('model = "gpt-5"\n', encoding="utf-8")

    section = doctor.Section("Stale")
    assert doctor.check_stale_injections(section) == []
    assert section.checks[0].status == doctor.OK


def test_fix_stale_injections_restores_toml_from_its_own_backup(tmp_path):
    """--fix must look for config.toml.bak, not with_suffix(".json.bak").

    The old name computation turned config.toml into config.json.bak, missed
    the real backup, and fell through to deleting a user file that had a
    restorable original.
    """
    codex_config = tmp_path / "config.toml"
    codex_config.write_text("_ca_injected = true\n", encoding="utf-8")
    backup = tmp_path / "config.toml.bak"
    backup.write_text('model = "gpt-5"\n', encoding="utf-8")

    doctor.fix_stale_injections([codex_config])

    assert codex_config.read_text(encoding="utf-8") == 'model = "gpt-5"\n'
    assert not backup.exists()


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
    from core.constants import ENGINES
    from core.services import mcp_service

    monkeypatch.setattr(
        mcp_service,
        "list_servers",
        _mcp_servers(
            dict.fromkeys(ENGINES, ["fs"])
        ),
    )
    section = doctor.Section("Parity")

    doctor.check_mcp_drift(section)

    assert section.checks[0].status == doctor.OK


def test_mcp_drift_names_the_engines_a_server_is_on(monkeypatch):
    from core.services import mcp_service

    monkeypatch.setattr(
        mcp_service,
        "list_servers",
        _mcp_servers({"claude": ["fs"], "codex": [], "opencode": [], "codebuddy": []}),
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


# --- Windows junction probe -------------------------------------------------
#
# The probe used to run in the project root and clean up with Path.exists(),
# which follows a junction to its target and so reports False for a dangling
# one. A leftover then made every later `mklink /j` fail with "file already
# exists", so the check reported a permanent, self-inflicted false failure.


def test_junction_probe_leaves_nothing_in_the_project_root(tmp_path):
    section = doctor.Section("Env")
    doctor.check_symlink_capability(section, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_junction_probe_sweeps_a_dangling_legacy_probe(tmp_path, monkeypatch):
    """A dangling leftover must not be mistaken for missing capability."""
    removed: list[Path] = []
    monkeypatch.setattr(doctor, "is_windows_link", lambda p: True)
    monkeypatch.setattr(doctor, "_remove_probe_dir", lambda p: removed.append(p))

    stale = tmp_path / ".ca_doctor_link_probe"
    stale.mkdir()
    doctor._sweep_legacy_probes(tmp_path)

    assert removed == [stale]


def test_sweep_never_removes_a_directory_with_real_content(tmp_path, monkeypatch):
    """Only ever reclaim a link or an empty dir -- never user content."""
    removed: list[Path] = []
    monkeypatch.setattr(doctor, "is_windows_link", lambda p: False)
    monkeypatch.setattr(doctor, "_remove_probe_dir", lambda p: removed.append(p))

    occupied = tmp_path / ".ca_doctor_target_probe"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("not ours", encoding="utf-8")
    doctor._sweep_legacy_probes(tmp_path)

    assert removed == []
    assert (occupied / "keep.txt").exists()


def test_temp_prompt_check_targets_the_dir_engines_actually_write_to(tmp_path):
    """It used to probe <project>/.ca_prompt.tmp, which nothing writes any more."""
    section = doctor.Section("Env")
    doctor.check_temp_file(section, tmp_path)

    assert section.checks[0].status == doctor.OK
    assert doctor.TEMP_PROMPT_DIRNAME in section.checks[0].detail
    assert not (tmp_path / ".ca_prompt.tmp").exists()


def test_display_width_counts_cjk_as_two_columns():
    """Section titles are translated, and _render rules them to this width;
    a len()-based rule underlines a Chinese heading to half its size."""
    assert doctor._display_width("Runtime") == 7
    assert doctor._display_width("运行环境") == 8
    assert doctor._display_width("CodeAgent 健康检查") == 18


def test_every_translated_section_title_has_a_width():
    """Guards the rule length for whichever language doctor renders in."""
    i18n.set_language("zh")
    titles = [s.title for s in doctor.get_doctor_sections(fix=False)]
    assert titles and all(doctor._display_width(x) >= len(x) for x in titles)


# --- first-run config seeding -----------------------------------------------
#
# config.json is gitignored, so a fresh clone had none, and the in-memory
# fallback carries no `groups` -- which mounted zero skills while the report
# still looked healthy.


def test_missing_config_points_at_a_repair_that_exists(tmp_path):
    section = doctor.Section("Config")
    assert doctor.check_config(section, tmp_path) is None
    assert section.checks[0].status == doctor.FAIL
    assert "ca doctor --fix" in section.checks[0].fix_hint


def test_fix_seeds_config_from_the_tracked_template(tmp_path, monkeypatch):
    """--fix turns the reported failure into a working config, using the real
    seeding path rather than a stand-in for it."""
    (tmp_path / "config.example.json").write_text(
        '{"groups": {"common": {"skills": ["base/x"]}}}', encoding="utf-8"
    )
    # get_default_config_path / get_bundled_resource_root both resolve from
    # CODE_ROOT; point them at the fixture so the real function runs.
    monkeypatch.setattr(resource_locator, "CODE_ROOT", tmp_path)
    monkeypatch.setenv("CA_CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setenv("CODEAGENT_RESOURCE_ROOT", str(tmp_path))

    section = doctor.Section("Config")
    cfg = doctor.check_config(section, tmp_path, fix=True)

    assert cfg is not None
    assert section.checks[0].status == doctor.OK
    assert (tmp_path / "config.json").exists()
    assert cfg["groups"]["common"]["skills"] == ["base/x"]


def test_seeding_never_overwrites_an_existing_config(tmp_path, monkeypatch):
    """The file holds the user's groups and project registry."""
    (tmp_path / "config.example.json").write_text('{"groups": {}}', encoding="utf-8")
    existing = tmp_path / "config.json"
    existing.write_text('{"mine": true}', encoding="utf-8")
    monkeypatch.setenv("CA_CONFIG_PATH", str(existing))
    monkeypatch.setenv("CODEAGENT_RESOURCE_ROOT", str(tmp_path))

    assert resource_locator.seed_config_if_missing(tmp_path) is None
    assert existing.read_text(encoding="utf-8") == '{"mine": true}'


def test_zero_skills_warns_instead_of_reporting_green(tmp_path, monkeypatch):
    """ "Skills (0 declared) -- all resolved" read as healthy while the
    product's headline feature was mounting nothing."""
    for directory in ("skills", "prompt", "hooks", "plugins"):
        (tmp_path / directory).mkdir()
    monkeypatch.chdir(tmp_path)

    section = doctor.Section("Context")
    doctor.check_skills_resolution(
        section, tmp_path, {"groups": {"codeagent": {"skills": []}}}
    )

    skills_check = [c for c in section.checks if "Skills" in c.label][0]
    assert skills_check.status == doctor.WARN
    assert "no skills will be mounted" in skills_check.detail
    # The hint must not promise --fix: seeding only applies to a missing file.
    assert "--fix" not in skills_check.fix_hint


def test_every_supported_engine_is_probed():
    """A gap here is invisible: the engine simply never appears in the report.

    codebuddy was missing for exactly that reason -- launchable, resumable,
    offered in the terminal picker, and absent from the health check, so a
    broken install produced no diagnosis and a missing one produced no hint.
    """
    from core.constants import ENGINES
    from core.doctor import ENGINE_BINARIES, ENGINE_INSTALL_HINTS

    assert set(ENGINE_BINARIES) == set(ENGINES)
    assert set(ENGINE_INSTALL_HINTS) == set(ENGINES)
