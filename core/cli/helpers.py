"""Helpers extracted from the former 1500-line ``ca_launcher.py``.

Pure-python utilities — project discovery, config, proxy, ports — with
no Click dependency so they can be imported from any layer without
circular imports.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

from core.console import configure_console_encoding
from core.constants import ENGINES  # noqa: F401
from core.host_env import child_environ
from core.i18n import ENV_VAR as CA_LANG_ENV  # noqa: F401
from core.i18n import resolve_language, t  # noqa: F401
from core.logging_config import configure_root_logging
from core.resource_locator import (
    CODE_ROOT,
    get_default_config_path,
    seed_config_if_missing,
)
from core.services.config_service import ConfigService


def init_cli_runtime() -> None:
    """Configure console encoding and root logging — call once at CLI entry.

    Previously executed at import time (side effect), now explicit so
    ``import core.cli.helpers`` is pure and test collection does not mutate
    global ``sys.stderr`` or the root logger. ``configure_root_logging``
    remains idempotent via its internal ``_configured`` flag.
    """

    configure_console_encoding()
    configure_root_logging()


FALLBACK_ENGINE = "opencode"


def _installed_root() -> Path:
    return CODE_ROOT


def _looks_like_project_root(path: Path) -> bool:
    return (
        (path / "pyproject.toml").exists()
        and (path / "core").is_dir()
        and (path / "engines").is_dir()
        and (path / "web" / "frontend" / "package.json").exists()
    )


def _project_root() -> Path:
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        return _installed_root()
    for candidate in (cwd, *cwd.parents):
        if _looks_like_project_root(candidate):
            return candidate
    return _installed_root()


def load_config() -> dict:
    """Load config via ``ConfigService`` — single source of truth.

    Previously this did a shallow ``{**default, **json.load}`` that
    dropped nested defaults (e.g. ``proxy.host`` when only ``proxy.port``
    was set). Now it delegates to ``ConfigService`` (utf-8-sig, mtime
    cache, atomic writes) and deep-merges top-level defaults.
    """

    root = _project_root()
    default_config: dict = {
        "default_mode": "local",
        "language": "auto",
        "proxy": {"host": "127.0.0.1", "port": 1087},
    }
    service = ConfigService(get_default_config_path(root))
    config, warnings = service.get_config()
    if warnings:
        print(t("config.load_failed", error=warnings[0]))
        return default_config
    if not config:
        return default_config
    # Shallow merge for top-level, deep-merge for known nested dicts
    merged = {**default_config, **config}
    if isinstance(default_config.get("proxy"), dict) and isinstance(
        config.get("proxy"), dict
    ):
        merged["proxy"] = {**default_config["proxy"], **config["proxy"]}
    return merged


def is_tcp_port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def find_available_port(start_port: int = 8524) -> int:
    port = start_port
    while port < 9000:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    return start_port


def _extract_proxy_candidates(proxy_cfg: object) -> list[tuple[str, int]]:
    if isinstance(proxy_cfg, list):
        return [
            (e.get("host", "127.0.0.1"), int(e["port"]))
            for e in proxy_cfg
            if isinstance(e, dict) and "port" in e
        ]
    if not isinstance(proxy_cfg, dict):
        proxy_cfg = {}
    host = proxy_cfg.get("host", "127.0.0.1")  # type: ignore[union-attr]
    port = proxy_cfg.get("port")  # type: ignore[union-attr]
    ports: list[int] = ([int(port)] if port is not None else []) + [
        3065,
        3067,
        3066,
        1087,
    ]
    return list(dict.fromkeys((host, p) for p in ports))  # type: ignore[arg-type]


def _select_active_proxy(candidates: list[tuple[str, int]]) -> tuple[str, int]:
    for host, port in candidates:
        if is_tcp_port_open(host, port):
            return host, port
    return candidates[0] if candidates else ("127.0.0.1", 3065)


def build_proxy_env(config: dict) -> tuple[dict[str, str], str, int, str]:
    proxy_cfg = config.get("proxy", {})
    candidates = _extract_proxy_candidates(proxy_cfg)
    proxy_host, selected_port = _select_active_proxy(candidates)
    proxy_scheme = "socks5" if selected_port == 3066 else "http"
    proxy_url = f"{proxy_scheme}://{proxy_host}:{selected_port}"
    child_env = child_environ()
    child_env["HTTP_PROXY"] = proxy_url
    child_env["HTTPS_PROXY"] = proxy_url
    child_env["ALL_PROXY"] = proxy_url
    return child_env, proxy_host, selected_port, proxy_scheme


def _ensure_project_on_path(root: Path) -> None:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _is_path_registered(cwd: Path, root: Path, registry: list) -> bool:
    if cwd == root or root in cwd.parents:
        return True
    for item in registry:
        raw_path = item.get("path")
        if not raw_path:
            continue
        try:
            mapping_path = Path(raw_path).resolve()
        except Exception:
            continue
        if cwd == mapping_path or mapping_path in cwd.parents:
            return True
    return False


def _ensure_project_registered(root: Path, config: dict) -> None:
    cwd = Path.cwd().resolve()
    registry = config.get("project_registry", [])
    if _is_path_registered(cwd, root, registry):
        return
    if os.environ.get("CA_SKIP_AUTO_REGISTER"):
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(t("project.unregistered_hint", cwd=cwd), file=sys.stderr)
        return
    groups = list(config.get("groups", {}).keys()) or ["common"]
    print(t("project.unregistered_title", cwd=cwd))
    print(t("project.pick_group"))
    for i, g in enumerate(groups, 1):
        print(f"  {i}. {g}")
    print(t("project.new_group_option"))
    print(t("project.skip_option"))
    choice = input("> ").strip().lower()
    if not choice:
        return
    is_new_group = False
    if choice == "n":
        new_name = (
            input(t("project.new_group_prompt")).strip().lower().replace(" ", "-")
        )
        if not new_name:
            print(t("project.no_group_name"))
            return
        chosen_group = new_name
        is_new_group = new_name not in config.get("groups", {})
    else:
        try:
            idx = int(choice) - 1
            if idx < 0:
                raise IndexError
            chosen_group = groups[idx]
        except (ValueError, IndexError):
            print(t("project.invalid_choice"))
            return
    config_path = get_default_config_path(root)
    service = ConfigService(config_path)

    def _modifier(cfg: dict) -> dict:
        if is_new_group:
            cfg.setdefault("groups", {})[chosen_group] = {
                "skills": [],
                "prompts": [],
                "hooks": [],
                "plugins": [],
            }
        reg = cfg.get("project_registry", [])
        reg.append({"path": str(cwd), "group": chosen_group})
        cfg["project_registry"] = reg
        return cfg

    service.modify_config(_modifier)
    persisted, _ = service.get_config()
    config["project_registry"] = persisted.get("project_registry", [])
    config["groups"] = persisted.get("groups", {})
    print(t("project.registered", group=chosen_group))


def _resolve_default_engine(config: dict, engine_script_map: dict) -> str:
    configured = config.get("default_engine")
    if configured is None:
        return FALLBACK_ENGINE
    name = str(configured).strip().lower()
    if name in engine_script_map:
        return name
    print(
        t(
            "engine.unknown_default",
            value=configured,
            known=", ".join(sorted(engine_script_map)),
            fallback=FALLBACK_ENGINE,
        ),
        file=sys.stderr,
    )
    return FALLBACK_ENGINE


def _launch_engine(ctx, args: list[str]):  # type: ignore[no-untyped-def]
    obj = ctx.ensure_object(dict)
    child_env = obj.get("child_env")
    engine_script_map = obj["engine_script_map"]

    seeded = seed_config_if_missing(obj["root"])
    if seeded is not None:
        print(t("config.seeded", path=seeded))
        obj["config"] = load_config()

    _ensure_project_registered(obj["root"], obj["config"])

    engine_name = _resolve_default_engine(obj["config"], engine_script_map)
    extra_params: list[str] = []

    if args:
        first_arg = args[0].lower()
        if first_arg in engine_script_map:
            engine_name = first_arg
            extra_params = list(args[1:])
        else:
            extra_params = list(args)

    if "-y" not in extra_params:
        extra_params.append("-y")

    if obj.get("yolo", True):
        print(t("engine.yolo_warning"))

    target_script = engine_script_map[engine_name]
    cmd = [sys.executable, target_script] + extra_params
    return subprocess.run(cmd, env=child_env).returncode


def _get_task_runner(root: Path):  # type: ignore[no-untyped-def]
    from core.services.runner_service import TaskRunner

    return TaskRunner(root)
