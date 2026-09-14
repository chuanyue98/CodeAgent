"""``ca sync``：把一个资源组的规范和技能写进各引擎的用户级位置。

同步一次之后，直接敲 ``claude``、``opencode`` 等原生命令也带着 CodeAgent 的
规范和技能，不必每次都经过 ``ca`` 启动。

规范写成用户规范文件（``CLAUDE.md``、``AGENTS.md`` ……）里一段带标记的托管块，
块外的内容原样保留；技能以链接形式挂进用户级技能目录，只动 CodeAgent 自己
清单里记录的链接，同名的用户文件一律不碰。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from core.constants import normalize_engine_name
from core.engine_base import BaseEngine
from core.link_manager import LinkManager
from core.logging_config import get_logger
from core.utils.atomic_write import atomic_write

logger = get_logger(__name__)

_BLOCK_END = "<!-- codeagent:end -->"
_BLOCK_RE = re.compile(
    r"<!-- codeagent:begin group=(?P<group>[^\s>]+) -->\n.*?<!-- codeagent:end -->\n?",
    re.DOTALL,
)
_BLOCK_NOTE = (
    "<!-- 由 `ca sync` 生成：修改请编辑 CodeAgent 的 prompt/ 后重新同步，"
    "`ca sync --remove` 可移除本段。 -->"
)


@dataclass(frozen=True)
class EngineTarget:
    engine: str
    memory_file: Path
    skills_dir: Path


@dataclass(frozen=True)
class SyncItem:
    engine: str
    kind: str  # "standards" | "skill"
    name: str
    action: str  # "write" | "update" | "unchanged" | "remove" | "conflict" | "failed"


def engine_targets(home: Path | None = None) -> dict[str, EngineTarget]:
    """各引擎用户级规范文件与技能目录的位置（均按引擎自带的发现规则确认过）。"""
    home = home if home is not None else Path.home()
    codex_home = (
        Path(os.environ["CODEX_HOME"])
        if os.environ.get("CODEX_HOME")
        else home / ".codex"
    )
    xdg = os.environ.get("XDG_CONFIG_HOME")
    opencode_dir = (Path(xdg) if xdg else home / ".config") / "opencode"
    codebuddy_dir = (
        Path(os.environ["CODEBUDDY_CONFIG_DIR"])
        if os.environ.get("CODEBUDDY_CONFIG_DIR", "").strip()
        else home / ".codebuddy"
    )
    # agy 的全局 customization root 是 ~/.gemini/config/，不是 ~/.gemini/。
    agy_dir = home / ".gemini" / "config"
    return {
        "claude": EngineTarget(
            "claude", home / ".claude" / "CLAUDE.md", home / ".claude" / "skills"
        ),
        "codex": EngineTarget("codex", codex_home / "AGENTS.md", codex_home / "skills"),
        "opencode": EngineTarget(
            "opencode", opencode_dir / "AGENTS.md", opencode_dir / "skills"
        ),
        "codebuddy": EngineTarget(
            "codebuddy", codebuddy_dir / "CODEBUDDY.md", codebuddy_dir / "skills"
        ),
        "antigravity": EngineTarget(
            "antigravity", agy_dir / "GEMINI.md", agy_dir / "skills"
        ),
    }


def render_block(group: str, standards: str) -> str:
    return (
        f"<!-- codeagent:begin group={group} -->\n{_BLOCK_NOTE}\n\n"
        f"{standards.strip()}\n{_BLOCK_END}\n"
    )


def replace_block(text: str, block: str) -> str:
    if _BLOCK_RE.search(text):
        return _BLOCK_RE.sub(lambda _match: block, text, count=1)
    if not text.strip():
        return block
    return text.rstrip("\n") + "\n\n" + block


def strip_block(text: str) -> str:
    stripped = _BLOCK_RE.sub("", text, count=1)
    return stripped.rstrip("\n") + "\n" if stripped.strip() else ""


def synced_group(memory_file: Path) -> str | None:
    """*memory_file* 里托管块对应的资源组；没有同步过时返回 ``None``。"""
    try:
        text = memory_file.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _BLOCK_RE.search(text)
    return match.group("group") if match else None


def is_synced(engine: str, group: str) -> bool:
    """*engine* 的用户级位置是否已经同步了 *group*，启动器据此跳过重复注入。"""
    target = engine_targets().get(normalize_engine_name(engine))
    return target is not None and synced_group(target.memory_file) == group


class _GroupEngine(BaseEngine):
    """按指定资源组解析规范和技能，而不是按当前目录所属的组。"""

    def __init__(self, group: str | None):
        super().__init__("sync", "")
        self.group = group or str(self.full_config.get("default_group", "common"))

    def get_current_project_group(self) -> str:
        return self.group


def sync(
    group: str | None = None,
    engines: list[str] | None = None,
    remove: bool = False,
    dry_run: bool = False,
    home: Path | None = None,
) -> tuple[str, list[SyncItem]]:
    """把 *group* 同步到 *engines*（默认全部）的用户级位置，返回 (组名, 逐项结果)。

    ``remove=True`` 撤掉 CodeAgent 写入的托管块和技能链接。

    Raises:
        ValueError: 资源组或引擎名不存在。
    """
    resources = _GroupEngine(group)
    known_groups = resources.full_config.get("groups", {})
    if not remove and resources.group not in known_groups:
        raise ValueError(
            f"Unknown resource group {resources.group!r}; known: {', '.join(sorted(known_groups)) or '-'}"
        )

    targets = engine_targets(home)
    selected = (
        [normalize_engine_name(name) for name in engines] if engines else list(targets)
    )
    unknown = [name for name in selected if name not in targets]
    if unknown:
        raise ValueError(f"Unknown engine: {', '.join(unknown)}")

    standards = "" if remove else resources.assemble_standards()
    skills = [] if remove else resources.resolve_skill_sources()

    items: list[SyncItem] = []
    for name in selected:
        target = targets[name]
        items.append(_sync_standards(target, resources.group, standards, dry_run))
        items.extend(_sync_skills(resources.link_manager, target, skills, dry_run))
    return resources.group, items


def _sync_standards(
    target: EngineTarget, group: str, standards: str, dry_run: bool
) -> SyncItem:
    path = target.memory_file
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = ""

    updated = (
        replace_block(current, render_block(group, standards))
        if standards
        else strip_block(current)
    )
    if updated == current:
        action = "unchanged"
    elif not standards:
        action = "remove"
    elif _BLOCK_RE.search(current):
        action = "update"
    else:
        action = "write"

    if not dry_run and updated != current:
        # 撤销后即使只剩空内容也保留文件：它可能是用户自己建的空文件。
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, updated)
    return SyncItem(target.engine, "standards", str(path), action)


def _sync_skills(
    links: LinkManager,
    target: EngineTarget,
    skills: list[tuple[str, Path]],
    dry_run: bool,
) -> list[SyncItem]:
    link_dir = target.skills_dir
    manifest = links.load_manifest(link_dir) if link_dir.is_dir() else {}
    desired = {name for name, _ in skills}
    items = [
        SyncItem(target.engine, "skill", name, "remove")
        for name in sorted(set(manifest) - desired)
    ]

    if not dry_run:
        if skills:
            link_dir.mkdir(parents=True, exist_ok=True)
            links.remove_stale_managed_links(link_dir, desired)
        else:
            links.cleanup_link_dir(link_dir)

    for name, source in skills:
        dest = link_dir / name
        if links.managed_link_matches(dest, source):
            action = "unchanged"
        elif (dest.exists() or dest.is_symlink()) and name not in manifest:
            action = "conflict"
        else:
            action = "update" if name in manifest else "write"

        if not dry_run and action in ("write", "update"):
            try:
                links.ensure_managed_link(source, dest, link_dir)
            except Exception as exc:
                logger.warning(
                    "Failed to link skill %r into %s: %s", name, link_dir, exc
                )
                action = "failed"
        items.append(SyncItem(target.engine, "skill", name, action))
    return items
