"""增量摄取：让持久化索引跟上引擎文件的变化。

每一步都是"枚举来源 → 比对版本令牌 → 只解析变了的 → 写库/删库"。全程逐个
会话处理，解析完立刻写库并释放，因此内存不随历史总量增长。

三个跨会话的收尾动作在写库之后统一做：codex 的父子关系（来自它自己的
lineage 库）、antigravity 的子会话项目继承、以及子代理标题（来自父会话记录
的启动描述）。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

from core.logging_config import get_logger
from core.session_history.index_store import (
    LAST_SYNC_KEY,
    SessionIndex,
    SourceRef,
    session_key,
)
from core.session_history.models import UnifiedSession
from core.session_history.parse_cache import _parser_fingerprint
from core.session_history.parsers.opencode_parser import parse_opencode_session
from core.session_history.session_finder import _deduplicate_sessions
from core.session_history.sources import (
    ENGINE_PARSERS,
    codex_lineage,
)

logger = get_logger(__name__)

_PARSER_FINGERPRINT_KEY = "parser_fingerprint"

#: 读路径据此判断"该不该顺手同步一下"。取一个比一次页面刷新略短的值：既不会
#: 每个请求都去 stat 全量文件，也不会让刚开的会话长时间看不到。
DEFAULT_STALE_SECONDS = 10.0

Enumerator = Callable[[Path | None], Iterator[SourceRef]]
Parser = Callable[[Path], UnifiedSession | None]


def _parse_ref(
    ref: SourceRef,
    parser: Parser,
    connection: sqlite3.Connection | None,
) -> UnifiedSession | None:
    """按来源类型解析；OpenCode 的"来源"是库里的一个会话行。"""
    if ref.engine == "opencode":
        return parse_opencode_session(
            ref.session_id_hint, Path(ref.source_file), connection=connection
        )
    return parser(Path(ref.source_file))


class SessionIndexer:
    """把引擎文件同步进 :class:`SessionIndex`。"""

    def __init__(self, index: SessionIndex, home: Path | None = None):
        self._index = index
        self._home = home
        self._lock = threading.Lock()
        self._syncing = False
        self._last_finished = 0.0

    @property
    def index(self) -> SessionIndex:
        return self._index

    def sync(self, *, force: bool = False) -> None:
        """跑一次增量同步。已在同步时直接返回（单飞）。"""
        if not self._lock.acquire(blocking=False):
            return
        try:
            self._sync_locked(force=force)
        except Exception:
            # 索引是派生数据：同步失败就保持现状、用旧的查询结果，绝不能让
            # 一次摄取错误把读路径带崩。
            logger.exception("Session index sync failed")
        finally:
            self._syncing = False
            self._last_finished = time.monotonic()
            self._lock.release()

    def sync_if_stale(self, max_age: float = DEFAULT_STALE_SECONDS) -> bool:
        """后台触发一次同步并立即返回；刚同步过则什么都不做。

        返回是否真的启动了同步（测试用）。热读端点据此在"每个请求都 stat"
        和"永远看不到新会话"之间取一个折中。
        """
        if self._syncing:
            return False
        last = self._index.get_meta(LAST_SYNC_KEY)
        try:
            if last and time.time() - float(last) < max_age:
                return False
        except (TypeError, ValueError):
            pass
        threading.Thread(target=self.sync, daemon=True).start()
        return True

    # ------------------------------------------------------------------

    def _sync_locked(self, *, force: bool) -> None:
        self._syncing = True
        if self._index.closed:
            return
        fingerprint = _parser_fingerprint()
        stored = self._index.get_meta(_PARSER_FINGERPRINT_KEY)
        if force or stored != fingerprint:
            if stored is not None and stored != fingerprint:
                logger.info("Parser fingerprint changed; rebuilding session index")
            self._index.clear_all()
            self._index.set_meta(_PARSER_FINGERPRINT_KEY, fingerprint)

        for engine, (enumerator, parser) in ENGINE_PARSERS.items():
            if self._index.closed:
                return
            try:
                self._sync_engine(engine, enumerator, parser)
            except Exception:
                # 一个引擎的坏文件/坏库不该拖住其余引擎，更不该让整轮同步白跑。
                logger.exception("Failed to sync engine %s into the session index", engine)

        if self._index.closed:
            return
        self._apply_codex_lineage()
        self._inherit_parent_projects()
        self._reconcile_subagent_titles()
        self._index.delete_orphan_sessions()
        self._index.set_meta(LAST_SYNC_KEY, str(int(time.time())))

    def _sync_engine(self, engine: str, enumerator: Enumerator, parser: Parser) -> None:
        refs: dict[str, SourceRef] = {}
        for ref in enumerator(self._home):
            refs[ref.source_key] = ref
        existing = self._index.source_versions(engine)
        changed = [r for key, r in refs.items() if existing.get(key) != r.version_token]
        removed = [key for key in existing if key not in refs]
        if not changed and not removed:
            return

        connection = self._open_engine_connection(engine, refs)
        try:
            parsed: dict[str, UnifiedSession | None] = {}
            for ref in changed:
                parsed[ref.source_key] = _parse_ref(ref, parser, connection)

            # 一个逻辑会话可能有多个来源（codex 续跑会新写一个 rollout 文件）。
            # 变更其一就要把兄弟来源一起取齐，交给与 finder 相同的合并逻辑。
            for key in {
                session_key(s.engine.value, s.session_id)
                for s in parsed.values()
                if s is not None
            }:
                for source in self._index.sources_for_session(key):
                    if source in parsed or source not in refs:
                        continue
                    parsed[source] = _parse_ref(refs[source], parser, connection)

            self._write_groups(engine, refs, parsed)
        finally:
            if connection is not None:
                connection.close()

        for source in removed:
            self._index.remove_source(source)

    def _open_engine_connection(
        self, engine: str, refs: dict[str, SourceRef]
    ) -> sqlite3.Connection | None:
        """OpenCode 的会话都在一个库里，整轮同步复用一个只读连接。"""
        if engine != "opencode" or not refs:
            return None
        db_path = next(iter(refs.values())).source_file
        try:
            connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.Error:
            return None
        # 解析器按列名取值，连接必须给 Row 工厂。
        connection.row_factory = sqlite3.Row
        return connection

    def _write_groups(
        self,
        engine: str,
        refs: dict[str, SourceRef],
        parsed: dict[str, UnifiedSession | None],
    ) -> None:
        groups: dict[str, list[tuple[str, UnifiedSession]]] = {}
        for source, session in parsed.items():
            if session is None:
                continue
            key = session_key(session.engine.value, session.session_id)
            groups.setdefault(key, []).append((source, session))

        for key, items in groups.items():
            merged = _deduplicate_sessions([s for _, s in items])[0]
            # 路径直接给出的父子关系（claude/codebuddy）；合并会丢掉它。
            for source, _ in items:
                if refs[source].parent_session_id:
                    merged.parent_session_id = refs[source].parent_session_id
                    break
            self._index.write_session(merged)
            for source, _ in items:
                ref = refs[source]
                self._index.upsert_source(replace(ref, session_key=key))
            # 父会话重解析后，它给子代理的启动描述可能变了，子标题要重算。
            if merged.subagent_titles:
                self._index.reset_children_titles(engine, merged.session_id)

        # 解析不出会话的来源也要登记：否则每次同步都会重解析一遍空文件。
        for source, session in parsed.items():
            if session is not None:
                continue
            empty_ref = refs.get(source)
            if empty_ref is not None:
                self._index.upsert_source(replace(empty_ref, session_key=""))

    def _apply_codex_lineage(self) -> None:
        """Codex 的父子/代理信息来自它自己的库，路径里看不出来。"""
        lineage = codex_lineage(self._home)
        for session_id, (parent, agent) in lineage.items():
            self._index.set_session_parent(
                session_key("codex", session_id), parent, agent
            )

    def _inherit_parent_projects(self) -> None:
        """antigravity 的子会话项目路径常为空，从父继承（父可能后到，跑两轮）。"""
        for _ in range(2):
            if self._index.inherit_parent_projects("antigravity") == 0:
                break

    def _reconcile_subagent_titles(self) -> None:
        """用父会话记录的启动描述给子代理命名。"""
        for key, engine, session_id, parent_id, _fallback in (
            self._index.unresolved_subagents()
        ):
            raw = self._index.get_subagent_titles_json(session_key(engine, parent_id))
            if not raw:
                continue
            try:
                titles = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(titles, dict):
                continue
            title = titles.get(session_id.removeprefix("agent-")) or titles.get(
                session_id
            )
            if title:
                self._index.set_session_title(key, str(title))


# ----------------------------------------------------------------------
# 进程内单例
# ----------------------------------------------------------------------

_indexer: SessionIndexer | None = None
_indexer_lock = threading.Lock()


def get_indexer() -> SessionIndexer | None:
    """返回绑定了进程内索引的摄取器；索引不可用时返回 None。"""
    global _indexer
    from core.session_history.index_store import get_index

    index = get_index()
    if index is None:
        return None
    with _indexer_lock:
        if _indexer is None or _indexer.index is not index:
            _indexer = SessionIndexer(index)
        return _indexer


def reset_indexer_for_tests() -> None:
    global _indexer
    with _indexer_lock:
        _indexer = None
