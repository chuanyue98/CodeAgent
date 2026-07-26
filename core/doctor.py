#!/usr/bin/env python3
"""ca doctor — CodeAgent health self-check."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import click

from core.hook_scanner import get_hooks_to_inject
from core.plugin_scanner import get_plugins_to_mount
from core.services.config_service import ConfigService

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
    checks: List[Check] = field(default_factory=list)

    def add(
        self, status: str, label: str, detail: str = "", fix_hint: str = ""
    ) -> None:
        self.checks.append(Check(status, label, detail, fix_hint))


# ── Engine binary map ─────────────────────────────────────────────────────────

ENGINE_BINARIES = {
    "claude": ["claude", "claude.cmd"],
    "gemini": ["gemini", "gemini.cmd"],
    "opencode": ["opencode", "opencode.cmd"],
    "codex": ["codex", "codex.cmd"],
}

ENGINE_INSTALL_HINTS = {
    "claude": "npm install -g @anthropic-ai/claude-code",
    "gemini": "npm install -g @google/gemini-cli",
    "opencode": "npm install -g opencode-ai",
    "codex": "npm install -g @openai/codex",
}

# ── Individual check functions ────────────────────────────────────────────────


def check_python(section: Section) -> None:
    ver = sys.version_info
    label = f"Python {ver.major}.{ver.minor}.{ver.micro}"
    if ver >= (3, 13):
        section.add(OK, label)
    elif ver >= (3, 10):
        section.add(WARN, label, "CodeAgent requires Python 3.13+", "Upgrade Python")
    else:
        section.add(
            FAIL, label, "Unsupported Python version", "Upgrade to Python 3.13+"
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
            section.add(OK, f"Engine: {engine}", found)
        else:
            section.add(
                WARN,
                f"Engine: {engine}",
                "binary not found in PATH",
                ENGINE_INSTALL_HINTS.get(engine, ""),
            )


def check_config(section: Section, root: Path) -> Optional[dict]:
    config_path = root / "config.json"
    config_service = ConfigService(config_path)
    cfg, warnings = config_service.get_config()

    for warning in warnings:
        section.add(WARN, "config.json", warning)

    if not cfg:
        if not config_path.exists():
            section.add(
                FAIL,
                "config.json",
                "file not found",
                "Run: ca (first launch creates defaults)",
            )
        else:
            section.add(FAIL, "config.json", "failed to load or parse configuration")
        return None

    section.add(OK, "config.json", "valid configuration")
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
            section.add(OK, label, f"{len(subdirs)} subdirectories")
        else:
            section.add(WARN, label, "directory not found")


def check_skills_resolution(section: Section, root: Path, cfg: dict) -> None:
    """Verify every skill declared in the current group can be found on disk."""

    try:
        # Use a minimal stand-in to get resolution logic without launching
        engine = _LightweightResolver(root, cfg)
        project_type = engine.get_current_project_group()
        section.add(INFO, f"Active project group: {project_type}")

        skills, warnings = engine.get_skills_to_mount()
        for w in warnings:
            section.add(WARN, "Skill Scanner", w)

        skill_roots = engine._get_skill_search_roots()

        missing = []
        for name in skills:
            found = any((r / name).exists() for r in skill_roots)
            if not found:
                missing.append(name)

        total = len(skills)
        if not missing:
            section.add(OK, f"Skills ({total} declared)", "all resolved")
        else:
            section.add(
                WARN,
                f"Skills ({total} declared, {len(missing)} missing)",
                ", ".join(missing),
                "Check skills/ directory or config.json groups",
            )
    except Exception as e:
        section.add(WARN, "Skills resolution", f"could not evaluate: {e}")


def check_hooks_resolution(section: Section, root: Path, cfg: dict) -> None:
    try:
        engine = _LightweightResolver(root, cfg)
        project_type = engine.get_current_project_group()
        hooks, warnings = engine.get_hooks_to_inject()
        for w in warnings:
            section.add(WARN, "Hook Scanner", w)

        declared = cfg.get("groups", {}).get(project_type, {}).get("hooks", [])
        missing = []
        for name in declared:
            if not any(h.get("name") == name.split("/")[-1] for h in hooks):
                missing.append(name)

        if not missing:
            section.add(OK, f"Hooks ({len(hooks)} resolved)")
        else:
            section.add(
                WARN,
                f"Hooks ({len(declared)} declared, {len(missing)} unresolved)",
                ", ".join(missing),
                "Check hooks/ directory or metadata.json files",
            )
    except Exception as e:
        section.add(WARN, "Hooks resolution", f"could not evaluate: {e}")


def check_plugins_resolution(section: Section, root: Path, cfg: dict) -> None:
    try:
        engine = _LightweightResolver(root, cfg)
        project_type = engine.get_current_project_group()
        plugins, warnings = engine.get_plugins_to_mount()
        for w in warnings:
            section.add(WARN, "Plugin Scanner", w)

        declared = cfg.get("groups", {}).get(project_type, {}).get("plugins", [])
        missing = []
        for name in declared:
            key = name.split("/")[-1]
            if not any(p.get("name") == key for p in plugins):
                missing.append(name)

        if not missing:
            section.add(OK, f"Plugins ({len(plugins)} resolved)")
        else:
            section.add(
                WARN,
                f"Plugins ({len(declared)} declared, {len(missing)} unresolved)",
                ", ".join(missing),
                "Check plugins/ directory",
            )
    except Exception as e:
        section.add(WARN, "Plugins resolution", f"could not evaluate: {e}")


def check_temp_file(section: Section, root: Path) -> None:
    tmp = root / ".ca_prompt.tmp"
    try:
        tmp.write_text("probe", encoding="utf-8")
        tmp.unlink()
        section.add(OK, "Temp prompt file writable", str(tmp))
    except OSError as e:
        section.add(
            FAIL,
            "Temp prompt file",
            f"not writable: {e}",
            "Check directory permissions",
        )


def check_proxy(section: Section, cfg: dict) -> None:
    proxy_cfg = cfg.get("proxy")
    if not proxy_cfg:
        section.add(INFO, "Proxy", "not configured (use --proxy flag to enable)")
        return

    from ca_launcher import _extract_proxy_candidates, is_tcp_port_open

    candidates = _extract_proxy_candidates(proxy_cfg)
    reachable = [(h, p) for h, p in candidates if is_tcp_port_open(h, p)]
    if reachable:
        h, p = reachable[0]
        section.add(OK, f"Proxy {h}:{p}", "reachable")
    else:
        all_str = ", ".join(f"{h}:{p}" for h, p in candidates)
        section.add(
            WARN,
            "Proxy",
            f"none of the configured addresses reachable ({all_str})",
            "Start your proxy or update config.json",
        )


def check_symlink_capability(section: Section, root: Path) -> None:
    """On Windows, verify we can create directory junctions."""
    if os.name != "nt":
        section.add(OK, "Symlink capability", "Unix (symlinks available)")
        return

    # Try mklink /j — works without elevated privileges
    test_target = root / ".ca_doctor_target_probe"
    test_link = root / ".ca_doctor_link_probe"
    try:
        test_target.mkdir(exist_ok=True)
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/j", str(test_link), str(test_target)],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            section.add(OK, "Windows junction support", "available (no admin required)")
        else:
            section.add(
                WARN,
                "Windows junction support",
                "mklink /j failed — skill linking may not work",
                "Enable Developer Mode or run as Administrator",
            )
    except Exception as e:
        section.add(WARN, "Windows junction support", str(e))
    finally:
        if test_link.exists():
            subprocess.run(["cmd", "/c", "rmdir", str(test_link)], capture_output=True)
        if test_target.exists():
            test_target.rmdir()


def check_stale_injections(section: Section) -> List[Path]:
    """Find stale .ca_injected settings files left by previous crashed sessions."""
    stale: List[Path] = []
    cwd = Path.cwd()

    candidates = [
        cwd / ".claude" / "settings.json",
        cwd / ".gemini" / "settings.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("_ca_injected"):
                stale.append(path)
        except Exception:
            continue

    if stale:
        names = ", ".join(p.name for p in stale)
        section.add(
            WARN,
            "Stale injections",
            f"settings still contain _ca_injected marker: {names}",
            "Run: ca doctor --fix  (auto-restores from .bak backups)",
        )
    else:
        section.add(OK, "Stale injections", "none found")
    return stale


# ── Fix routine ───────────────────────────────────────────────────────────────


def fix_stale_injections(stale: List[Path]) -> None:
    for settings_path in stale:
        backup = settings_path.with_suffix(".json.bak")
        if backup.exists():
            os.replace(str(backup), str(settings_path))
            print(f"  Restored {settings_path} from backup")
        else:
            # No backup means ca created the file — safe to remove
            settings_path.unlink()
            print(f"  Removed injected {settings_path}")


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
                self_inner.temp_prompt_name = ".ca_prompt.tmp"
                from core.skill_scanner import SkillScanner
                from core.prompt_scanner import PromptScanner
                from core.hook_scanner import HookScanner
                from core.plugin_scanner import PluginScanner

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

    def get_skills_to_mount(self) -> tuple[List[str], List[str]]:
        data = self._engine.get_skills_to_mount()
        _, warnings = self._engine.skill_scanner.scan()
        return data, warnings

    def get_hooks_to_inject(self) -> tuple[List[dict], List[str]]:
        project_type = self._engine.get_current_project_group()
        return get_hooks_to_inject(
            self._engine.full_config,
            self._engine.hook_scanner,
            project_type=project_type,
        )

    def get_plugins_to_mount(self) -> tuple[List[dict], List[str]]:
        project_type = self._engine.get_current_project_group()
        return get_plugins_to_mount(
            self._engine.full_config,
            self._engine.plugin_scanner,
            project_type=project_type,
        )

    def __getattr__(self, name):
        return getattr(self._engine, name)


# ── Renderer ─────────────────────────────────────────────────────────────────


def _render(sections: List[Section]) -> int:
    """Print results and return number of failures.

    Uses ``click.style``/``click.echo`` so status markers are color-coded in
    a real terminal, while automatically degrading to plain text when output
    isn't a TTY (piped to a file, CI logs, etc.) -- click detects that for us.
    """
    failures = 0
    warnings = 0
    for section in sections:
        click.echo(f"\n  {section.title}")
        click.echo("  " + "─" * len(section.title))
        for c in section.checks:
            status = click.style(
                c.status, fg=_STATUS_COLORS.get(c.status), bold=True
            )
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
                f"  Result: {failures} failure(s), {warnings} warning(s) — run 'ca doctor --fix' for auto-repairs",
                fg="red",
                bold=True,
            )
        )
    elif warnings:
        click.echo(
            click.style(
                f"  Result: {warnings} warning(s) — check the hints above",
                fg="yellow",
            )
        )
    else:
        click.echo(click.style("  Result: all checks passed", fg="green", bold=True))
    click.echo()
    return failures


# ── Public entry point ────────────────────────────────────────────────────────


def get_doctor_sections(fix: bool = False) -> list[Section]:
    """Run all health checks and return structured Section results.

    Does NOT print anything. The caller is responsible for rendering or
    serializing the sections.
    """
    root = Path(__file__).resolve().parent.parent

    s1 = Section("Runtime")
    check_python(s1)
    check_engines(s1)

    s2 = Section("Configuration")
    cfg = check_config(s2, root)
    if cfg is not None:
        check_directories(s2, root)

    s3 = Section("Context Resolution")
    if cfg is not None:
        check_skills_resolution(s3, root, cfg)
        check_hooks_resolution(s3, root, cfg)
        check_plugins_resolution(s3, root, cfg)
    else:
        s3.add(INFO, "Skipped", "config.json could not be loaded")

    s4 = Section("Environment")
    check_temp_file(s4, root)
    if cfg is not None:
        check_proxy(s4, cfg)
    check_symlink_capability(s4, root)

    s5 = Section("Session Integrity")
    stale = check_stale_injections(s5)
    if fix and stale:
        print("  Applying fixes...")
        fix_stale_injections(stale)
        print("  Done. Re-run 'ca doctor' to verify.")
        print()

    return [s1, s2, s3, s4, s5]


def run_doctor(fix: bool = False) -> int:
    """Run all health checks. Returns exit code (0 = OK, 1 = failures)."""
    click.echo()
    click.echo(click.style("  CodeAgent Health Check", bold=True))
    click.echo("  " + "=" * 22)
    if fix:
        click.echo("  --fix mode: auto-repairable issues will be resolved")
    sections = get_doctor_sections(fix=fix)
    failures = _render(sections)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run_doctor())
