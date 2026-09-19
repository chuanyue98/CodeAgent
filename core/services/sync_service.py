"""``ca sync``：把一个资源组的规范落到当前项目，技能挂到各引擎的用户级位置。

规范写进项目根的 ``AGENTS.md``，一段带标记的托管块，块外内容原样保留。
不按引擎 fan-out 到 ``CLAUDE.md`` / ``CODEBUDDY.md`` / ``GEMINI.md``：各引擎
都原生读 ``AGENTS.md``（依据见 :data:`STANDARDS_FILENAME` 处的注释），
antigravity 则项目级一个都不读，代它写没有意义。

技能仍然挂到各引擎的**用户级**技能目录。技能的目录布局各引擎不同，而且启动器
本来就会按当前项目临时挂一份（``_LinksMixin.ensure_skills_link``），用户级那份
是"不经 ``ca`` 直接敲原生命令"时的兜底。两处用同一套 manifest 机制，但落在
不同目录，所以互不干扰。

``scope="user"`` 是旧行为（规范写进各引擎的用户级规范文件），只保留给
``ca sync --user`` 清理历史遗留的托管块用。
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

#: 项目级规范落盘的文件名。claude / codebuddy / opencode / codex 都原生读取项目根
#: 的这个文件，依据是 2026-09-19 的实测：临时目录里只放一个 ``AGENTS.md``，
#: 用 headless 模式追问"你的口令是什么"，claude 与 opencode 都答对了；codebuddy
#: 在被它自己启动的会话里直接把该文件当 project instructions 带进了系统提示；
#: codex 的 ``AGENTS.md`` 本来就是它定义的。antigravity 则连给它 ``GEMINI.md``
#: 都答 ``UNKNOWN``，其全局配置里也查不到任何记忆文件机制，故不为它落盘。
STANDARDS_FILENAME = "AGENTS.md"

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
    engine: str  # 规范条目为空串：它不属于某个引擎
    kind: str  # "standards" | "skill"
    name: str
    action: str  # "write" | "update" | "unchanged" | "remove" | "conflict" | "failed"


def standards_file(root: Path | None = None) -> Path:
    """规范落盘位置：项目根的 ``AGENTS.md``。"""
    return (root if root is not None else Path.cwd()) / STANDARDS_FILENAME


def engine_targets(home: Path | None = None) -> dict[str, EngineTarget]:
    """各引擎用户级规范文件与技能目录的位置（均按引擎自带的发现规则确认过）。

    技能仍落在这里；规范文件只有 ``ca sync --user`` 还用得到。
    """
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
    scope: str = "project",
    root: Path | None = None,
    home: Path | None = None,
) -> tuple[str, list[SyncItem]]:
    """把 *group* 落盘，返回 (组名, 逐项结果)。

    ``scope="project"``（默认）把规范写进 ``root`` 下的 ``AGENTS.md``；
    ``scope="user"`` 写进各引擎的用户级规范文件，只用于清理旧同步。
    技能一律挂到各引擎的用户级技能目录。

    ``remove=True`` 撤掉 CodeAgent 写入的托管块和技能链接。

    Raises:
        ValueError: 资源组、引擎名或 scope 不存在。
    """
    if scope not in ("project", "user"):
        raise ValueError(f"Unknown scope {scope!r}; expected 'project' or 'user'")

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
    if scope == "user":
        for name in selected:
            memory_file = targets[name].memory_file
            items.append(
                _sync_standards(
                    memory_file, str(memory_file), resources.group, standards, dry_run
                )
            )
    else:
        items.append(
            _sync_standards(
                standards_file(root),
                STANDARDS_FILENAME,
                resources.group,
                standards,
                dry_run,
            )
        )

    for name in selected:
        items.extend(
            _sync_skills(
                resources.link_manager, name, targets[name].skills_dir, skills, dry_run
            )
        )
    return resources.group, items


def _sync_standards(
    path: Path, label: str, group: str, standards: str, dry_run: bool
) -> SyncItem:
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
        if not updated and _BLOCK_RE.search(current):
            # 文件里原本只有我们的块（多半是 `ca sync` 建出来的），删掉块后
            # 留一个空文件是噪音——原本就不存在的东西，还原成不存在。
            path.unlink(missing_ok=True)
        else:
            # 撤销后即使只剩空内容也保留文件：它可能是用户自己建的空文件。
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, updated)
    return SyncItem("", "standards", label, action)


def _sync_skills(
    links: LinkManager,
    engine: str,
    link_dir: Path,
    skills: list[tuple[str, Path]],
    dry_run: bool,
) -> list[SyncItem]:
    manifest = links.load_manifest(link_dir) if link_dir.is_dir() else {}
    desired = {name for name, _ in skills}
    items = [
        SyncItem(engine, "skill", name, "remove")
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
        items.append(SyncItem(engine, "skill", name, action))
    return items
