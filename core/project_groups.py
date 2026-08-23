"""Resolves which resource group applies to a directory.

A ``project_registry`` entry is a *rule*, not an inventory row: it maps a path
prefix onto a resource group, and the longest matching prefix wins. Registering
``E:/demo -> web`` therefore covers every repository under ``E:/demo``, while a
more specific ``E:/demo/CodeAgent -> codeagent`` overrides it for that one.

This lives on its own so the CLI (``ConfigManager``) and the Web UI's agent
gateway share one implementation. They used to each have their own — the CLI
matched by prefix, the gateway by exact equality — so the same config produced
different resource sets depending on which half of the app you were in, and the
gateway's mismatch failed silently as an empty group.
"""

from __future__ import annotations

from pathlib import Path


def _resolved(path: str) -> Path | None:
    try:
        return Path(path).expanduser().resolve()
    except Exception:
        # Registry paths are user-editable text; an unresolvable entry should
        # skip its rule rather than break resolution for every other one.
        return None


def resolve_project_group(
    path: str | Path,
    registry: list[dict] | None,
) -> str | None:
    """Names the group configured for ``path``, or None when no rule matches.

    Args:
        path: The directory being worked in.
        registry: ``config["project_registry"]`` — entries of ``{path, group}``.

    Returns:
        The group of the longest-prefix rule covering ``path``, or None.
    """
    target = _resolved(str(path))
    if target is None or not registry:
        return None

    best_group: str | None = None
    best_length = -1

    for entry in registry:
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        group = entry.get("group")
        if not isinstance(raw_path, str) or not isinstance(group, str):
            continue

        rule = _resolved(raw_path)
        if rule is None:
            continue
        if target != rule and rule not in target.parents:
            continue

        # Compare on the resolved path's length: a deeper rule is necessarily
        # longer, and this is what makes the more specific one win.
        length = len(rule.as_posix())
        if length > best_length:
            best_length = length
            best_group = group

    return best_group
