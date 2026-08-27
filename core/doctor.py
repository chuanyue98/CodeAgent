#!/usr/bin/env python3
"""ca doctor — CodeAgent health self-check."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import click

from core.constants import TEMP_PROMPT_DIRNAME
from core.hook_scanner import get_hooks_to_inject
from core.i18n import t
from core.link_manager import is_windows_link
from core.plugin_scanner import get_plugins_to_mount
from core.resource_locator import CODE_ROOT, seed_config_if_missing
from core.services.config_service import ConfigService
from core.settings_manager import SettingsFile

# ── Status symbols ────────────────────────────────────────────────────────────

OK = "[OK]"
WARN = "[!] "
FAIL = "[X] "
INFO = "[i] "

_STATUS_COLORS = {
    OK: "green",
    WARN: "yellow",
    FAIL: "red",
    INFO: "cyan",
}

# ── Result model ──────────────────────────────────────────────────────────────


@dataclass
class Check:
    status: str  # OK / WARN / FAIL / INFO
    label: str
    detail: str = ""
    fix_hint: str = ""


@dataclass
class Section:
    title: str
    checks: list[Check] = field(default_factory=list)

    def add(
        self, status: str, label: str, detail: str = "", fix_hint: str = ""
    ) -> None:
        self.checks.append(Check(status, label, detail, fix_hint))


# ── Engine binary map ─────────────────────────────────────────────────────────

#: Keep in step with :data:`core.constants.ENGINES` -- an engine missing here
#: is one the health check silently says nothing about, so a user with it
#: broken gets no diagnosis and a user without it gets no install hint.
ENGINE_BINARIES = {
    "claude": ["claude", "claude.cmd"],
    "opencode": ["opencode", "opencode.cmd"],
    "codex": ["codex", "codex.cmd"],
    "codebuddy": ["codebuddy", "codebuddy.cmd"],
}

ENGINE_INSTALL_HINTS = {
    "claude": "npm install -g @anthropic-ai/claude-code",
    "opencode": "npm install -g opencode-ai",
    "codex": "npm install -g @openai/codex",
    "codebuddy": "npm install -g @tencent-ai/codebuddy-code",
}

# ── Individual check functions ────────────────────────────────────────────────


def check_python(section: Section) -> None:
    ver = sys.version_info
    label = f"Python {ver.major}.{ver.minor}.{ver.micro}"
    if ver >= (3, 13):
        section.add(OK, label)
    elif ver >= (3, 10):
        section.add(WARN, label, t("doctor.python_too_old"), t("doctor.python_upgrade"))
    else:
        section.add(
            FAIL,
            label,
            t("doctor.python_unsupported"),
            t("doctor.python_upgrade_to"),
        )


def check_engines(section: Section) -> None:
    is_windows = sys.platform == "win32"
    for engine, candidates in ENGINE_BINARIES.items():
        found = None
        for name in candidates:
            if not is_windows and name.lower().endswith((".cmd", ".bat", ".exe")):
                continue
            found = shutil.which(name)
            if found:
                break
        if found:
            section.add(OK, t("doctor.engine_label", engine=engine), found)
        else:
            section.add(
                WARN,
                t("doctor.engine_label", engine=engine),
                t("doctor.engine_missing"),
                ENGINE_INSTALL_HINTS.get(engine, ""),
            )


def check_config(section: Section, root: Path, fix: bool = False) -> dict | None:
    config_path = root / "config.json"

    # A fresh clone has no config.json -- it is gitignored -- and the old hint
    # ("Run: ca, first launch creates defaults") was untrue: nothing wrote the
    # file. --fix now seeds it from the tracked template, so the repair the
    # result line advertises actually applies to this failure.
    if fix and not config_path.exists():
        seeded = seed_config_if_missing(root)
        if seeded is not None:
            print(t("doctor.config_seeded", path=seeded))

    config_service = ConfigService(config_path)
    cfg, warnings = config_service.get_config()

    for warning in warnings:
        section.add(WARN, "config.json", warning)

    if not cfg:
        if not config_path.exists():
            section.add(
                FAIL,
                "config.json",
                t("doctor.config_not_found"),
                t("doctor.config_run_fix"),
            )
        else:
            section.add(FAIL, "config.json", t("doctor.config_unparsable"))
        return None

    section.add(OK, "config.json", t("doctor.config_valid"))
    return cfg


def check_directories(section: Section, root: Path) -> None:
    dirs = {
        "prompt/": root / "prompt",
        "skills/": root / "skills",
        "hooks/": root / "hooks",
        "plugins/": root / "plugins",
        "tasks/": root / "tasks",
    }
    for label, path in dirs.items():
        if path.exists():
            subdirs = [d for d in path.iterdir() if d.is_dir()]
            section.add(OK, label, t("doctor.dir_subdirs", count=len(subdirs)))
        else:
            section.add(WARN, label, t("doctor.dir_missing"))


def check_skills_resolution(section: Section, root: Path, cfg: dict) -> None:
    """Verify every skill declared in the current group can be found on disk."""

    try:
        # Use a minimal stand-in to get resolution logic without launching
        engine = _LightweightResolver(root, cfg)
        project_type = engine.get_current_project_group()
        section.add(INFO, t("doctor.active_group", group=project_type))

        skills, warnings = engine.get_skills_to_mount()
        for w in warnings:
            section.add(WARN, t("doctor.skill_scanner"), w)

        skill_roots = engine._get_skill_search_roots()

        missing = []
        for name in skills:
            found = any((r / name).exists() for r in skill_roots)
            if not found:
                missing.append(name)

        total = len(skills)
        if total == 0:
            # "Skills (0 declared) -- all resolved" used to render green, which
            # is literally true and badly misleading: the Skills system is the
            # product's headline feature, and a config with no groups mounted
            # nothing while the report looked entirely healthy.
            section.add(
                WARN,
                t("doctor.skills_declared", total=0),
                t("doctor.skills_none_detail", group=project_type),
                t("doctor.skills_none_hint", group=project_type),
            )
        elif not missing:
            section.add(
                OK,
                t("doctor.skills_declared", total=total),
                t("doctor.all_resolved"),
            )
        else:
            section.add(
                WARN,
                t("doctor.skills_missing", total=total, missing=len(missing)),
                ", ".join(missing),
                t("doctor.skills_hint"),
            )
    except Exception as e:
        section.add(
            WARN, t("doctor.skills_error"), t("doctor.could_not_evaluate", error=e)
        )


def check_hooks_resolution(section: Section, root: Path, cfg: dict) -> None:
    try:
        engine = _LightweightResolver(root, cfg)
        project_type = engine.get_current_project_group()
        hooks, warnings = engine.get_hooks_to_inject()
        for w in warnings:
            section.add(WARN, t("doctor.hook_scanner"), w)

        declared = cfg.get("groups", {}).get(project_type, {}).get("hooks", [])
        missing = []
        for name in declared:
            if not any(h.get("name") == name.split("/")[-1] for h in hooks):
                missing.append(name)

        if not missing:
            section.add(OK, t("doctor.hooks_resolved", count=len(hooks)))
        else:
            section.add(
                WARN,
                t(
                    "doctor.hooks_unresolved",
                    declared=len(declared),
                    missing=len(missing),
                ),
                ", ".join(missing),
                t("doctor.hooks_hint"),
            )
    except Exception as e:
        section.add(
            WARN, t("doctor.hooks_error"), t("doctor.could_not_evaluate", error=e)
        )


def check_plugins_resolution(section: Section, root: Path, cfg: dict) -> None:
    try:
        engine = _LightweightResolver(root, cfg)
        project_type = engine.get_current_project_group()
        plugins, warnings = engine.get_plugins_to_mount()
        for w in warnings:
            section.add(WARN, t("doctor.plugin_scanner"), w)

        declared = cfg.get("groups", {}).get(project_type, {}).get("plugins", [])
        missing = []
        for name in declared:
            key = name.split("/")[-1]
            if not any(p.get("name") == key for p in plugins):
                missing.append(name)

        if not missing:
            section.add(OK, t("doctor.plugins_resolved", count=len(plugins)))
        else:
            section.add(
                WARN,
                t(
                    "doctor.plugins_unresolved",
                    declared=len(declared),
                    missing=len(missing),
                ),
                ", ".join(missing),
                t("doctor.plugins_hint"),
            )
    except Exception as e:
        section.add(
            WARN, t("doctor.plugins_error"), t("doctor.could_not_evaluate", error=e)
        )


def check_temp_file(section: Section, root: Path) -> None:
    """Verifies the directory engines actually write assembled prompts into.

    This used to probe ``<project>/.ca_prompt.tmp``, a location
    ``_PromptMixin.write_temp_prompt`` stopped using when it moved to
    ``mkstemp`` under the system temp directory — so the check could pass
    while the real target was unwritable, and vice versa.
    """
    prompt_dir = Path(tempfile.gettempdir()) / TEMP_PROMPT_DIRNAME
    try:
        prompt_dir.mkdir(parents=True, exist_ok=True)
        fd, probe_name = tempfile.mkstemp(dir=prompt_dir, prefix="ca_doctor.")
        os.close(fd)
        Path(probe_name).unlink(missing_ok=True)
        section.add(OK, t("doctor.temp_prompt_ok"), str(prompt_dir))
    except OSError as e:
        section.add(
            FAIL,
            t("doctor.temp_prompt_label"),
            t("doctor.temp_prompt_failed", error=e),
            t("doctor.temp_prompt_hint", path=prompt_dir),
        )


def check_proxy(section: Section, cfg: dict) -> None:
    proxy_cfg = cfg.get("proxy")
    if not proxy_cfg:
        section.add(INFO, t("doctor.proxy_label"), t("doctor.proxy_unset"))
        return

    from core.cli.helpers import _extract_proxy_candidates, is_tcp_port_open

    candidates = _extract_proxy_candidates(proxy_cfg)
    reachable = [(h, p) for h, p in candidates if is_tcp_port_open(h, p)]
    if reachable:
        h, p = reachable[0]
        section.add(
            OK, f"{t('doctor.proxy_label')} {h}:{p}", t("doctor.proxy_reachable")
        )
    else:
        all_str = ", ".join(f"{h}:{p}" for h, p in candidates)
        section.add(
            WARN,
            t("doctor.proxy_label"),
            t("doctor.proxy_unreachable", addresses=all_str),
            t("doctor.proxy_hint"),
        )


#: Probe names used by earlier versions, which created them in the project
#: root. Left behind, a dangling one made every later run report a false
#: failure (see :func:`_sweep_legacy_probes`).
_LEGACY_PROBE_NAMES = (".ca_doctor_link_probe", ".ca_doctor_target_probe")


def _remove_probe_dir(path: Path) -> None:
    """Removes a probe directory or junction, dangling ones included.

    ``Path.exists()`` follows a junction to its target and so reports False
    for a dangling one — the exact case that used to leave probes behind.
    ``os.path.lexists`` inspects the link itself instead.
    """
    if not os.path.lexists(path):
        return
    if os.name == "nt":
        # Best effort cleanup; a hung rmdir must not hang all of `ca doctor`.
        try:
            subprocess.run(
                ["cmd", "/c", "rmdir", str(path)],
                capture_output=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            pass
    else:
        try:
            path.unlink()
        except OSError:
            try:
                path.rmdir()
            except OSError:
                pass


def _sweep_legacy_probes(root: Path) -> None:
    """Clears probe artifacts an older doctor may have left in the repo root.

    These are unambiguously ours (fixed names, always empty or a junction to
    an empty directory), and a dangling one is actively harmful: it makes
    ``mklink /j`` fail with "file already exists", so the junction check
    reports a permanent false failure, and ``git status`` warns on every run.
    Nothing here can self-heal, so sweep it unconditionally.
    """
    for name in _LEGACY_PROBE_NAMES:
        candidate = root / name
        if not os.path.lexists(candidate):
            continue
        # Only ever remove a link or an empty directory — never real content.
        if not is_windows_link(candidate) and any(candidate.iterdir()):
            continue
        _remove_probe_dir(candidate)


def check_symlink_capability(section: Section, root: Path) -> None:
    """On Windows, verify we can create directory junctions."""
    if os.name != "nt":
        section.add(OK, t("doctor.symlink_label"), t("doctor.symlink_unix"))
        return

    _sweep_legacy_probes(root)

    # Probe in a private temp directory rather than the project root: it keeps
    # the check out of the user's working tree (and out of `git status`), and
    # a freshly made directory cannot collide with a previous run's leftovers.
    probe_dir = Path(tempfile.mkdtemp(prefix="ca-doctor-junction-"))
    test_target = probe_dir / "target"
    test_link = probe_dir / "link"
    try:
        test_target.mkdir()
        # mklink /j needs no elevated privileges; a non-zero exit here is a
        # real capability failure rather than leftover state.
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/j", str(test_link), str(test_target)],
            capture_output=True,
            check=False,
            timeout=30,
        )
        if result.returncode == 0:
            section.add(OK, t("doctor.junction_label"), t("doctor.junction_ok"))
        else:
            detail = (
                result.stderr.decode(errors="replace").strip()
                or result.stdout.decode(errors="replace").strip()
                or t("doctor.junction_exit_code", code=result.returncode)
            )
            section.add(
                WARN,
                t("doctor.junction_label"),
                t("doctor.junction_failed", detail=detail),
                t("doctor.junction_hint"),
            )
    except Exception as e:
        section.add(WARN, t("doctor.junction_label"), str(e))
    finally:
        _remove_probe_dir(test_link)
        shutil.rmtree(probe_dir, ignore_errors=True)


def check_hook_delivery(section: Section, root: Path, cfg: dict) -> None:
    """Reports which engines will actually run the configured hooks.

    Resolving a hook only means CodeAgent found it — whether the engine then
    honours it is a separate question, and one that used to be invisible: a
    hook could be green in "Context Resolution" while silently doing nothing
    under the engine you were about to launch.
    """
    try:
        engine = _LightweightResolver(root, cfg)
        hooks, _ = engine.get_hooks_to_inject()
    except Exception as exc:
        section.add(
            WARN,
            t("doctor.hook_delivery_label"),
            t("doctor.could_not_evaluate", error=exc),
        )
        return

    if not hooks:
        section.add(
            INFO, t("doctor.hook_delivery_label"), t("doctor.hook_delivery_none")
        )
        return

    count = len(hooks)
    section.add(
        OK,
        t("doctor.hook_delivery_count", count=count),
        t("doctor.hook_delivery_supported"),
    )

    # codex only loads project-local config -- hooks included -- for projects
    # marked trusted in the user-level config. Untrusted, it starts normally
    # and drops them without an error.
    try:
        import tomlkit

        project = Path.cwd().resolve()
        user_config = Path.home() / ".codex" / "config.toml"
        trusted = False
        if user_config.exists():
            doc = tomlkit.parse(user_config.read_text(encoding="utf-8"))
            for key, value in (doc.get("projects", {}) or {}).items():
                try:
                    if Path(key).resolve() == project:
                        trusted = (
                            hasattr(value, "get")
                            and value.get("trust_level") == "trusted"
                        )
                        break
                except OSError:
                    continue

        if trusted:
            section.add(OK, t("doctor.codex_hooks_label"), t("doctor.codex_trusted"))
        else:
            section.add(
                WARN,
                t("doctor.codex_hooks_label"),
                t("doctor.codex_untrusted", project=project),
                t(
                    "doctor.codex_trust_hint",
                    project=project,
                    config=user_config,
                ),
            )
    except Exception as exc:
        section.add(
            INFO,
            t("doctor.codex_hooks_label"),
            t("doctor.codex_trust_unknown", error=exc),
        )


def check_mcp_drift(section: Section) -> None:
    """Reports MCP servers configured on some engines but not others.

    Adding a server to one engine and forgetting the rest is the exact drift
    `ca mcp sync` exists to fix, so surface it here instead of leaving the
    user to diff four native config files by hand.
    """
    try:
        from core.constants import ENGINES
        from core.services import mcp_service

        project = str(Path.cwd())
        by_engine: dict[str, set[str]] = {}
        for name in sorted(ENGINES):
            by_engine[name] = {
                entry["name"] for entry in mcp_service.list_servers(name, project)
            }
    except Exception as exc:
        section.add(
            WARN,
            t("doctor.mcp_drift_label"),
            t("doctor.could_not_evaluate", error=exc),
        )
        return

    everything = set().union(*by_engine.values()) if by_engine else set()
    if not everything:
        section.add(INFO, t("doctor.mcp_servers_label"), t("doctor.mcp_none"))
        return

    shared = set.intersection(*by_engine.values())
    drifted = sorted(everything - shared)
    if not drifted:
        section.add(
            OK,
            t("doctor.mcp_in_sync_label", count=len(shared)),
            t("doctor.mcp_in_sync"),
        )
        return

    detail = ", ".join(
        t(
            "doctor.mcp_drift_entry",
            name=name,
            engines=", ".join(e for e in sorted(by_engine) if name in by_engine[e]),
        )
        for name in drifted[:4]
    )
    if len(drifted) > 4:
        detail += t("doctor.mcp_drift_more", count=len(drifted) - 4)
    section.add(
        WARN,
        t("doctor.mcp_drift_count", count=len(drifted)),
        detail,
        t("doctor.mcp_drift_hint"),
    )


def check_stale_injections(section: Section) -> list[Path]:
    """Find stale .ca_injected settings files left by previous crashed sessions."""
    stale: list[Path] = []
    cwd = Path.cwd()

    candidates = [
        cwd / ".claude" / "settings.json",
        cwd / ".opencode" / "settings.json",
        cwd / ".codex" / "settings.json",
        # Codex reads hooks from config.toml -- that is where start_codex
        # injects and where a SIGKILLed run leaves its residue. settings.json
        # stays in the list only to sweep up pre-TOML leftovers.
        cwd / ".codex" / "config.toml",
    ]
    for path in candidates:
        if not path.exists():
            continue
        # SettingsFile parses JSON and TOML; a crashed codex injection lives
        # in config.toml, which json.load here used to silently skip.
        data = SettingsFile(path).load()
        if isinstance(data, dict) and data.get("_ca_injected"):
            stale.append(path)

    if stale:
        names = ", ".join(p.name for p in stale)
        section.add(
            WARN,
            t("doctor.stale_label"),
            t("doctor.stale_found", names=names),
            t("doctor.stale_hint"),
        )
    else:
        section.add(OK, t("doctor.stale_label"), t("doctor.stale_none"))
    return stale


# ── Fix routine ───────────────────────────────────────────────────────────────


def _injection_backup_path(settings_path: Path) -> Path:
    """Backup name matching SettingsFile.create_backup() for any suffix.

    ``with_suffix(".json.bak")`` only produced the right name for .json
    files; on config.toml it yielded config.json.bak and the real
    config.toml.bak was never found, so --fix fell through to deleting a
    file that had a restorable backup.
    """
    return settings_path.with_name(settings_path.name + ".bak")


def fix_stale_injections(stale: list[Path]) -> None:
    for settings_path in stale:
        backup = _injection_backup_path(settings_path)
        if backup.exists():
            os.replace(str(backup), str(settings_path))
            print(t("doctor.restored", path=settings_path))
        else:
            # No backup means ca created the file — safe to remove
            settings_path.unlink()
            print(t("doctor.removed_injected", path=settings_path))


def preview_stale_injections(stale: list[Path]) -> None:
    """Describe what fix_stale_injections() would do, without touching anything."""
    for settings_path in stale:
        backup = _injection_backup_path(settings_path)
        if backup.exists():
            print(t("doctor.would_restore", path=settings_path))
        else:
            print(t("doctor.would_remove", path=settings_path))


# ── Lightweight resolver (avoids running a real engine) ───────────────────────


class _LightweightResolver:
    """Thin wrapper around BaseEngine just for resolution queries."""

    def __init__(self, root: Path, cfg: dict):
        sys.path.insert(0, str(root))
        from core.engine_base import BaseEngine

        class _Stub(BaseEngine):
            def __init__(self_inner):
                self_inner.name = "doctor"
                self_inner.default_model = ""
                self_inner.root_dir = root
                from core.config_manager import ConfigManager

                self_inner.config_manager = ConfigManager(root)
                self_inner.config_manager.full_config = cfg
                self_inner.full_config = cfg
                from core.engine_base import EnvironmentManager

                self_inner.env_manager = EnvironmentManager(root)
                from core.hook_scanner import HookScanner
                from core.plugin_scanner import PluginScanner
                from core.prompt_scanner import PromptScanner
                from core.skill_scanner import SkillScanner

                resource_root = self_inner.config_manager.resolve_resource_root()
                self_inner.skill_scanner = SkillScanner(resource_root / "skills")
                self_inner.prompt_scanner = PromptScanner(resource_root / "prompt")
                self_inner.hook_scanner = HookScanner(
                    self_inner._get_hook_search_roots()
                )
                self_inner.plugin_scanner = PluginScanner(resource_root / "plugins")

            def execute(self_inner, *a, **kw):
                raise NotImplementedError

        self._engine = _Stub()

    def get_skills_to_mount(self) -> tuple[list[str], list[str]]:
        data = self._engine.get_skills_to_mount()
        _, warnings = self._engine.skill_scanner.scan()
        return data, warnings

    def get_hooks_to_inject(self) -> tuple[list[dict], list[str]]:
        project_type = self._engine.get_current_project_group()
        return get_hooks_to_inject(
            self._engine.full_config,
            self._engine.hook_scanner,
            project_type=project_type,
        )

    def get_plugins_to_mount(self) -> tuple[list[dict], list[str]]:
        project_type = self._engine.get_current_project_group()
        return get_plugins_to_mount(
            self._engine.full_config,
            self._engine.plugin_scanner,
            project_type=project_type,
        )

    def __getattr__(self, name):
        return getattr(self._engine, name)


# ── Renderer ─────────────────────────────────────────────────────────────────


def _display_width(text: str) -> int:
    """Terminal columns ``text`` occupies, not its character count.

    Section titles are translated, and CJK characters render two columns
    wide -- so a ``len()``-based rule underlines a Chinese heading to barely
    half its width.
    """
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _render(sections: list[Section]) -> int:
    """Print results and return number of failures.

    Uses ``click.style``/``click.echo`` so status markers are color-coded in
    a real terminal, while automatically degrading to plain text when output
    isn't a TTY (piped to a file, CI logs, etc.) -- click detects that for us.
    """
    failures = 0
    warnings = 0
    for section in sections:
        click.echo(f"\n  {section.title}")
        click.echo("  " + "─" * _display_width(section.title))
        for c in section.checks:
            status = click.style(c.status, fg=_STATUS_COLORS.get(c.status), bold=True)
            line = f"  {status}  {c.label}"
            if c.detail:
                line += f"  —  {c.detail}"
            click.echo(line)
            if c.fix_hint and c.status in (WARN, FAIL):
                click.echo(f"         ↳ {c.fix_hint}")
            if c.status == FAIL:
                failures += 1
            elif c.status == WARN:
                warnings += 1

    click.echo()
    if failures:
        click.echo(
            click.style(
                t("doctor.result_failures", failures=failures, warnings=warnings),
                fg="red",
                bold=True,
            )
        )
    elif warnings:
        click.echo(
            click.style(
                t("doctor.result_warnings", warnings=warnings),
                fg="yellow",
            )
        )
    else:
        click.echo(click.style(t("doctor.result_ok"), fg="green", bold=True))
    click.echo()
    return failures


# ── Public entry point ────────────────────────────────────────────────────────


def get_doctor_sections(fix: bool = False, dry_run: bool = False) -> list[Section]:
    """Run all health checks and return structured Section results.

    Does NOT print anything. The caller is responsible for rendering or
    serializing the sections.
    """
    root = CODE_ROOT

    s1 = Section(t("doctor.section_runtime"))
    check_python(s1)
    check_engines(s1)

    s2 = Section(t("doctor.section_configuration"))
    cfg = check_config(s2, root, fix=fix)
    if cfg is not None:
        check_directories(s2, root)

    s3 = Section(t("doctor.section_context"))
    if cfg is not None:
        check_skills_resolution(s3, root, cfg)
        check_hooks_resolution(s3, root, cfg)
        check_plugins_resolution(s3, root, cfg)
    else:
        s3.add(INFO, t("doctor.skipped"), t("doctor.skipped_no_config"))

    s4 = Section(t("doctor.section_environment"))
    check_temp_file(s4, root)
    if cfg is not None:
        check_proxy(s4, cfg)
    check_symlink_capability(s4, root)

    s5 = Section(t("doctor.section_parity"))
    if cfg is not None:
        check_hook_delivery(s5, root, cfg)
    check_mcp_drift(s5)

    s6 = Section(t("doctor.section_sessions"))
    stale = check_stale_injections(s6)
    if dry_run and stale:
        print(t("doctor.dry_run_banner"))
        preview_stale_injections(stale)
        print()
    elif fix and stale:
        print(t("doctor.applying_fixes"))
        fix_stale_injections(stale)
        print(t("doctor.fixes_done"))
        print()

    return [s1, s2, s3, s4, s5, s6]


def run_doctor(fix: bool = False, dry_run: bool = False) -> int:
    """Run all health checks. Returns exit code (0 = OK, 1 = failures)."""
    click.echo()
    title = t("doctor.title")
    click.echo(click.style(f"  {title}", bold=True))
    click.echo("  " + "=" * _display_width(title))
    if dry_run:
        click.echo(f"  {t('doctor.mode_dry_run')}")
    elif fix:
        click.echo(f"  {t('doctor.mode_fix')}")
    sections = get_doctor_sections(fix=fix, dry_run=dry_run)
    failures = _render(sections)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run_doctor())
