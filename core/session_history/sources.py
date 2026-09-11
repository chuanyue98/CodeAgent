"""各引擎的"来源枚举"：只找文件、算版本，不解析。

增量摄取的每一步都是"先枚举、再比对令牌、只解析变了的"。原来的
``find_*_sessions`` 把枚举、解析、富化（父子、标题）揉在一个返回 list 的函数
里，正是它逼着调用方把全部会话读进内存。这里把枚举单独拆出来，解析仍复用各
引擎现成的 ``parse_*_session``。

枚举一律**全局**（不加 project 过滤）：索引是全量的，过滤交给查询。
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from core.session_history.index_store import SourceRef
from core.session_history.parsers._subagents import subagent_files
from core.session_history.parsers.antigravity_parser import parse_antigravity_session
from core.session_history.parsers.claude_parser import parse_claude_session
from core.session_history.parsers.codebuddy_parser import parse_codebuddy_session
from core.session_history.parsers.codex_parser import (
    _thread_lineage,
    parse_codex_session,
)
from core.session_history.parsers.opencode_parser import (
    _NO_ROWS,
    _find_opencode_db,
    _session_versions,
    parse_opencode_session,
)
from core.utils.long_paths import list_dirs, list_files, long_path


def file_version(path: Path) -> str | None:
    """``"<mtime_ns>:<size>"``；读不到（文件消失/无权限）时 None。

    无权限等读不到的情况返回 None，让调用方当作"来源消失"处理，而不是抛错。
    """
    try:
        stat = os.stat(long_path(path))
    except OSError:
        return None
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _file_engine_sources(
    engine: str, projects_dir: Path
) -> Iterator[SourceRef]:
    """``<root>/<project>/<session>.jsonl`` + 其 ``subagents/**`` 的通用枚举。

    Claude Code 与 CodeBuddy 的目录结构一致，父子关系由路径直接决定。
    """
    if not projects_dir.exists():
        return
    for project_dir in list_dirs(projects_dir):
        if not project_dir.is_dir():
            continue
        candidates: list[tuple[Path, str]] = [
            (jsonl, "") for jsonl in list_files(project_dir, ".jsonl")
        ]
        for session_dir in list_dirs(project_dir):
            candidates.extend(subagent_files(session_dir))
        for jsonl_file, parent_session_id in candidates:
            version = file_version(jsonl_file)
            if version is None:
                continue
            yield SourceRef(
                source_key=f"{engine}:{jsonl_file}",
                engine=engine,
                source_file=str(jsonl_file),
                version_token=version,
                parent_session_id=parent_session_id,
            )


def enumerate_claude_sources(home: Path | None = None) -> Iterator[SourceRef]:
    yield from _file_engine_sources(
        "claude", (home or Path.home()) / ".claude" / "projects"
    )


def enumerate_codebuddy_sources(home: Path | None = None) -> Iterator[SourceRef]:
    yield from _file_engine_sources(
        "codebuddy", (home or Path.home()) / ".codebuddy" / "projects"
    )


def enumerate_codex_sources(home: Path | None = None) -> Iterator[SourceRef]:
    """``~/.codex/sessions/**/rollout-*.jsonl``。

    父子关系来自 ``state_5.sqlite``，不在路径里，由摄取阶段统一补齐。
    """
    base = (home or Path.home()) / ".codex" / "sessions"
    if not base.exists():
        return
    for jsonl_file in list_files(base, ".jsonl", recursive=True):
        version = file_version(jsonl_file)
        if version is None:
            continue
        yield SourceRef(
            source_key=f"codex:{jsonl_file}",
            engine="codex",
            source_file=str(jsonl_file),
            version_token=version,
        )


def enumerate_opencode_sources(home: Path | None = None) -> Iterator[SourceRef]:
    """OpenCode 的"来源"是单库里的一个 session 行。"""
    db_path = _find_opencode_db(home)
    if not db_path:
        return
    con = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        versions = _session_versions(con)
        rows = con.execute("SELECT id, time_updated FROM session").fetchall()
    except sqlite3.Error:
        return
    finally:
        if con is not None:
            con.close()

    for row in rows:
        session_id = row["id"]
        if not session_id:
            continue
        token = f"{row['time_updated'] or 0}:{versions.get(session_id, _NO_ROWS)}"
        yield SourceRef(
            source_key=f"opencode:{db_path}:{session_id}",
            engine="opencode",
            source_file=str(db_path),
            version_token=token,
            session_id_hint=str(session_id),
        )


def _antigravity_transcript(brain_dir: Path, session_id: str) -> Path | None:
    preferred = (
        brain_dir / session_id / ".system_generated" / "logs" / "transcript.jsonl"
    )
    if preferred.is_file():
        return preferred
    fallback = brain_dir / session_id / "transcript.jsonl"
    return fallback if fallback.is_file() else None


def antigravity_meta_version(home: Path | None = None) -> str:
    """元数据库（标题/项目/父子）的版本，用于让索引跟着它失效。"""
    base = (home or Path.home()) / ".gemini" / "antigravity-cli"
    return file_version(base / "conversation_summaries.db") or "absent"


def enumerate_antigravity_sources(home: Path | None = None) -> Iterator[SourceRef]:
    """元数据库列出的会话 + ``brain/`` 目录里没被收录的 transcript。

    transcript 的版本里带上元数据库版本：解析器会读那份库来取标题/项目/父子，
    库变了而 transcript 没变时也必须重解析，否则索引会停在旧元数据上。
    """
    base = (home or Path.home()) / ".gemini" / "antigravity-cli"
    if not base.exists():
        return
    meta_version = antigravity_meta_version(home)
    brain_dir = base / "brain"
    db_path = base / "conversation_summaries.db"

    seen: set[str] = set()
    if db_path.is_file():
        con = None
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            rows = con.execute("SELECT conversation_id FROM conversation_summaries")
            session_ids = [r["conversation_id"] for r in rows]
        except sqlite3.Error:
            session_ids = []
        finally:
            if con is not None:
                con.close()
        for session_id in session_ids:
            if not session_id or session_id in seen:
                continue
            transcript = _antigravity_transcript(brain_dir, session_id)
            if transcript is None:
                continue
            seen.add(session_id)
            yield _antigravity_ref(transcript, meta_version)

    if brain_dir.is_dir():
        for sess_dir in list_dirs(brain_dir):
            session_id = sess_dir.name
            if session_id in seen:
                continue
            transcript = _antigravity_transcript(brain_dir, session_id)
            if transcript is None:
                continue
            yield _antigravity_ref(transcript, meta_version)


def _antigravity_ref(transcript: Path, meta_version: str) -> SourceRef:
    version = file_version(transcript)
    token = f"{version}|meta={meta_version}" if version else f"absent|meta={meta_version}"
    return SourceRef(
        source_key=f"antigravity:{transcript}",
        engine="antigravity",
        source_file=str(transcript),
        version_token=token,
    )


def _raw(parser):
    """剥掉 ``@cached_file_parser`` 包装，取真正解析的那个函数。

    摄取绝不能经过 parse_cache：它会把每个解析结果常驻内存，正是本次要消灭
    的东西。装饰器把原函数挂在 ``__wrapped__`` 上；没被装饰的直接返回。
    """
    return getattr(parser, "__wrapped__", parser)


#: 引擎 -> (枚举函数, 裸解析函数)。
ENGINE_PARSERS = {
    "claude": (enumerate_claude_sources, _raw(parse_claude_session)),
    "codebuddy": (enumerate_codebuddy_sources, _raw(parse_codebuddy_session)),
    "codex": (enumerate_codex_sources, _raw(parse_codex_session)),
    "opencode": (enumerate_opencode_sources, parse_opencode_session),
    "antigravity": (enumerate_antigravity_sources, _raw(parse_antigravity_session)),
}


def codex_lineage(home: Path | None = None) -> dict[str, tuple[str, str]]:
    """``thread id -> (parent, agent)``；无库时为空。"""
    return _thread_lineage(home)


def codex_lineage_version(home: Path | None = None) -> str:
    base = (home or Path.home()) / ".codex"
    return file_version(base / "state_5.sqlite") or "absent"


def enumerate_all_sources(home: Path | None = None) -> Iterator[SourceRef]:
    """按固定顺序枚举所有引擎的来源。"""
    for engine in ("claude", "codebuddy", "codex", "opencode", "antigravity"):
        yield from ENGINE_PARSERS[engine][0](home)
