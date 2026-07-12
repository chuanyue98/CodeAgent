"""E2E-only reset route, mounted solely when ``CA_E2E=1`` is set.

Exposes ``POST /api/__e2e_reset`` which restores the isolated test
backend to a known-clean baseline between Playwright specs. Without that
gate, the route does not exist on the production app (404), so it can never
be hit accidentally in real usage.

What "clean" means here:
  - ``CA_CONFIG_PATH`` is rewritten to a minimal baseline (one registered
    project pointing at ``$HOME`` so McpPage has a cwd to shell out into,
    plus an empty ``codeagent`` group so gallery toggles have a target).
  - The four read-only resource roots (skills/hooks/plugins/prompts) are
    wiped and re-seeded from ``web/frontend/e2e/fixtures/`` so any test-
    written state (e.g. claude's ``.mcp.json`` written into a project dir)
    is discarded.

Schedules live inside ``config.json`` under the ``schedules`` key (see
ScheduleService), so rewriting config also clears them — no separate
schedule-store cleanup is needed.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.analytics.disk_cache import invalidate_cache
from core.web.resource_paths import ROOT_DIR, resolve_resource_path

router = APIRouter(prefix="/api", tags=["e2e"])

FIXTURES_DIR = ROOT_DIR / "web" / "frontend" / "e2e" / "fixtures"


def _baseline_config() -> dict:
    home = os.environ.get("HOME", "")
    registry = [{"path": home, "group": "codeagent"}] if home else []
    return {
        "project_registry": registry,
        "groups": {
            "codeagent": {"skills": [], "prompts": [], "hooks": [], "plugins": []},
        },
    }


def _reseed_root(root: Path, fixture_subdir: str) -> None:
    if root.exists():
        for child in root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        root.mkdir(parents=True, exist_ok=True)

    src = FIXTURES_DIR / fixture_subdir
    if not src.exists():
        return
    for item in src.iterdir():
        dst = root / item.name
        if item.is_dir():
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)


def _reseed_task_logs() -> None:
    tasks_root = resolve_resource_path("tasks", "CA_TASKS_ROOT")
    if tasks_root.exists():
        for child in tasks_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        tasks_root.mkdir(parents=True, exist_ok=True)

    dummy = tasks_root / "e2e-task.log"
    dummy.write_text(
        "[2026-07-12 10:00:00] E2E dummy log entry\n"
        "[2026-07-12 10:00:01] Task started: e2e-demo\n"
        "[2026-07-12 10:00:05] Task completed: e2e-demo\n",
        encoding="utf-8",
    )


@router.post("/__e2e_reset")
def e2e_reset() -> dict:
    if os.environ.get("CA_E2E") != "1":
        raise HTTPException(status_code=404, detail="Not Found")

    reset: list[str] = []

    config_path = Path(os.environ.get("CA_CONFIG_PATH", str(ROOT_DIR / "config.json")))
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(_baseline_config(), indent=2), encoding="utf-8")
    reset.append("config")

    _reseed_root(resolve_resource_path("skills", "CA_SKILLS_ROOT"), "skills")
    reset.append("skills")

    _reseed_root(resolve_resource_path("hooks", "CA_HOOKS_ROOT"), "hooks")
    reset.append("hooks")

    _reseed_root(resolve_resource_path("plugins", "CA_PLUGINS_ROOT"), "plugins")
    reset.append("plugins")

    _reseed_root(resolve_resource_path("prompt", "CA_PROMPTS_ROOT"), "prompts")
    reset.append("prompts")

    # Clean up and re-seed task logs so the Logs page has deterministic
    # content. All files under CA_TASKS_ROOT are removed, then a single
    # dummy log entry is written.
    _reseed_task_logs()
    # Seed a small analytics history so the Sessions / Audit / Analytics
    # pages have deterministic data to render and interact with (the
    # isolated backend otherwise starts with zero usage history).
    _seed_analytics_history()
    # Invalidate the analytics cache so get_analytics_data() re-reads
    # from the freshly seeded history instead of returning stale data.
    invalidate_cache()

    return {"ok": True, "reset": reset}


def _seed_analytics_history() -> None:
    history_path = Path.home() / ".ca_analytics_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "timestamp": "2026-07-01T10:00:00",
            "session_id": "e2e-session-claude",
            "model": "claude-3-5-sonnet",
            "input_tokens": 1200,
            "output_tokens": 800,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 100,
            "cost": 0.012,
            "project_path": "/tmp/e2e-claude-project",
            "target": "claude",
        },
        {
            "timestamp": "2026-07-02T14:30:00",
            "session_id": "e2e-session-gemini",
            "model": "gemini-1.5-pro",
            "input_tokens": 500,
            "output_tokens": 300,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "cost": 0.004,
            "project_path": "/tmp/e2e-gemini-project",
            "target": "gemini",
        },
    ]
    history_path.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8"
    )
