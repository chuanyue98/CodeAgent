"""Workspace registration and resource-snapshot resolution for the gateway.

Extracted verbatim from the monolithic ``agent_gateway.py``: pure logic with
no event-loop concerns, already covered by
``tests/test_gateway_workspace_resolution.py`` through the gateway facade.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

from core.logging_config import get_logger
from core.project_groups import resolve_project_group
from core.resource_locator import (
    CODE_ROOT,
    get_bundled_resource_root,
    resolve_resource_root_from_config,
)
from core.services.agent_gateway.errors import AgentGatewayError
from core.services.agent_protocol import ResourceSnapshot

if TYPE_CHECKING:
    from core.services.agent_gateway.gateway import AgentGateway

logger = get_logger(__name__)

# Resource kinds a group can declare; "prompts" is the only kind the Gateway
# currently injects (via adapters that declare supports_resource_injection).
INJECTED_KINDS = ("prompts",)
# Mirrors prompt_kit.EXCLUDED_PROMPT_FILES: non-standards docs that happen to
# live in a prompt group directory.
EXCLUDED_PROMPT_FILES = {"README.md", "IMPLEMENTATION_PLAN.md"}


def registered_workspace(gateway: AgentGateway, project_id: str) -> tuple[str, str]:
    """Resolve and validate a requested workspace against the registry.

    Returns ``(cwd, identity)``: ``cwd`` is the fully resolved path used
    to actually launch the provider CLI, while ``identity`` is the
    registry's own path string for that entry. The two can differ on
    Windows (``resolve()`` always normalizes to backslashes) or when the
    registry entry uses ``~``/relative segments -- callers must persist
    ``identity`` as the session's project_id so it stays byte-equal to
    what ``GET /api/projects`` returns for the frontend to match on.
    """
    config, warnings = gateway._config_service.get_config()
    if warnings:
        # A malformed config file degrades to whatever parsed (often
        # nothing); failing the request with a 500 here used to take
        # down session creation for an unrelated syntax error. The
        # registry lookup below already gives an actionable error.
        logger.warning("Config read failed: %s", warnings[0])
    requested = Path(project_id).expanduser().resolve()
    if not requested.is_dir():
        raise AgentGatewayError(
            "workspace_unavailable", "Selected workspace is unavailable"
        )
    # Exact match first, then the deepest registered ancestor. Requiring
    # an exact match made every subdirectory unusable, which also made
    # the longest-prefix group resolution in core.project_groups
    # unreachable from the Web UI: you could not start a session in a
    # subdirectory at all, so its group never had to be worked out.
    #
    # Ancestry is tested with `in .parents`, not a string prefix -- the
    # latter accepts /work/demo-old for a rule of /work/demo.
    best: tuple[int, str] | None = None
    for project in config.get("project_registry", []):
        if not isinstance(project, dict) or not isinstance(project.get("path"), str):
            continue
        try:
            registered = Path(project["path"]).expanduser().resolve()
        except (OSError, ValueError):
            continue
        if registered == requested:
            return str(requested), project["path"]
        if registered in requested.parents:
            depth = len(registered.parts)
            if best is None or depth > best[0]:
                best = (depth, project["path"])

    if best is not None:
        # The identity stays the *registered* path: it is what
        # GET /api/projects returns and what the frontend matches a
        # session against, while the cwd is where the CLI actually runs.
        return str(requested), best[1]

    raise AgentGatewayError(
        "workspace_not_registered",
        "Select a workspace registered in Settings before starting an agent",
    )


def resource_snapshot(
    gateway: AgentGateway, workspace: str, config: dict | None = None
) -> ResourceSnapshot:
    """Names the session's group configures, as a declaration.

    When :func:`assemble_system_prompt` succeeds for this snapshot it
    gains a ``digest`` receipt and ``applied_kinds``; otherwise clients
    must show these resources as configured-but-inactive.
    """
    if config is None:
        config, _warnings = gateway._config_service.get_config()
    # Longest-prefix, the same rule the CLI applies (core/project_groups).
    # This used to compare for exact equality, so a workspace covered by a
    # parent rule -- the whole point of registering `E:/demo -> web` once
    # instead of every repository under it -- resolved to no group at all,
    # and the session started with an empty resource set and no warning.
    group_name = resolve_project_group(workspace, config.get("project_registry"))
    definition = config.get("groups", {}).get(group_name or "", {})
    if not isinstance(definition, dict):
        definition = {}

    def values(key: str) -> list[str]:
        raw = definition.get(key, [])
        return (
            [item for item in raw if isinstance(item, str)]
            if isinstance(raw, list)
            else []
        )

    return ResourceSnapshot(
        group=group_name,
        skills=values("skills"),
        prompts=values("prompts"),
        hooks=values("hooks"),
        plugins=values("plugins"),
    )


def prompt_root(config: dict) -> Path:
    """Same resolution order as core.web.resource_paths, without the web import."""
    env_root = os.environ.get("CA_PROMPTS_ROOT")
    if env_root:
        return Path(env_root)
    resolved = resolve_resource_root_from_config(config, CODE_ROOT)
    base = resolved if resolved is not None else get_bundled_resource_root(CODE_ROOT)
    return Path(base) / "prompt"


def assemble_system_prompt(
    prompt_groups: list[str], config: dict
) -> tuple[str, list[dict]] | None:
    """Reads every markdown file behind the group's prompt names.

    Mirrors prompt_kit's per-group assembly (sorted ``*.md``, README and
    IMPLEMENTATION_PLAN excluded) but returns per-file segments so the
    receipt can name exactly which content entered the model, and omits
    the task / waiting-mode tail -- a system prompt is standing
    instruction, not a one-shot kickoff message.

    Returns ``(text, segments)``, or None when nothing could be read;
    None keeps the session honest (declared but not applied).
    """
    root = prompt_root(config)
    segments: list[dict] = []
    parts: list[str] = []
    for group in prompt_groups:
        group_dir = root / group
        md_files = sorted(group_dir.glob("*.md")) if group_dir.is_dir() else []
        contents: list[str] = []
        for path in md_files:
            if path.name in EXCLUDED_PROMPT_FILES:
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                logger.warning("Skipping unreadable prompt %s: %s", path, exc)
                continue
            if not content:
                continue
            contents.append(content)
            segments.append(
                {
                    "kind": "prompts",
                    "name": f"{group}/{path.stem}",
                    "path": str(path),
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "bytes": len(content.encode()),
                }
            )
        if contents:
            parts.append(f"### {group.capitalize()} Standards ###")
            parts.append("\n\n".join(contents))
    if not segments:
        return None
    return "\n\n".join(parts).strip(), segments
