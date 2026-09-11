"""持久化的会话索引（SQLite）。

在此之前，所有读路径都要先 :func:`find_all_sessions` 把每个引擎的 transcript
解析成 ``UnifiedSession``（含全部消息）并常驻内存：907 个会话 ≈ 253MB RSS，
冷启动 ≈ 2.8s。本模块用一张磁盘上的索引取代它——摄取时逐个会话解析、写入、
释放；读取只查需要的行，内存里不再留全量语料。

索引是**可重建的派生数据**，不是归档：真相仍在引擎原始文件里，删掉本文件重
新同步即可。这一点决定了三件事：schema 冲突时重建而不是报错、损坏时忽略而
不是崩溃、绝不作为唯一副本。

约定与 ``core/services/agent_store.py`` 保持一致：``schema_version`` 表 + 顺序
迁移、WAL、``foreign_keys``、单持久连接 + ``RLock``，读持锁、写在
``with lock, connection`` 内。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logging_config import get_logger
from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)
from core.session_history.paths import normalize_project_path

logger = get_logger(__name__)

SCHEMA_VERSION = 1

#: 记录"索引已经完整同步过一次"的元键。没有它就说明首轮构建还没跑完，读路径
#: 必须回退到原来的解析方式，而不是返回空结果。
LAST_SYNC_KEY = "last_sync_finished_at"

#: 换库位置 / 关掉索引的开关。关掉时读路径回退到 finder。
ENV_PATH = "CA_SESSION_INDEX_DB"
ENV_DISABLE = "CA_SESSION_INDEX"

#: 一次 audit 查询最多返回的事件数上限，避免误用把整库拖出来。
_MAX_AUDIT_LIMIT = 5000


def default_index_path() -> Path:
    """索引默认位置，与 agent-gateway.sqlite3 同目录。"""
    return Path.home() / ".codeagent" / "session-index.sqlite3"


def index_disabled() -> bool:
    """``CA_SESSION_INDEX=0`` 时整条索引路径关闭，读回退到 finder。"""
    return os.environ.get(ENV_DISABLE, "").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }


def to_epoch(value: str) -> int | None:
    """把会话里的 ISO 时间戳尽量解析成 UTC epoch 秒。

    与 ``core.web.routers.analytics._as_utc`` 同一套宽松规则：解析不了的返回
    None，调用方当作"不做范围过滤"，而不是把记录丢掉。
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


@dataclass(frozen=True)
class SourceRef:
    """一个物理来源文件/会话，以及它的版本令牌。

    版本令牌在"文件未变"时必须相等、"变了"时必须不同，通常就是
    ``(mtime_ns, size)``；OpenCode 这类单库引擎用每会话的计数。

    ``parent_session_id`` 只有能从路径直接看出来的引擎（claude/codebuddy）
    才会填；其余引擎的父子关系在解析后由各自的元数据补齐。
    """

    source_key: str
    engine: str
    source_file: str
    version_token: str
    parent_session_id: str = ""
    session_id_hint: str = ""
    session_key: str = ""


@dataclass(frozen=True)
class SessionSummary:
    """list 视图需要的一行，不含消息。"""

    session_key: str
    engine: str
    session_id: str
    project_path: str
    project_norm: str
    started_at: str
    ended_at: str
    last_activity: str
    message_count: int
    title: str
    model: str
    source_file: str
    parent_session_id: str
    agent: str

    def to_summary_dict(self) -> dict[str, Any]:
        """与 ``UnifiedSession.to_summary_dict()`` 同样的键，供 API 复用。"""
        return {
            "session_id": self.session_id,
            "engine": self.engine,
            "project_path": self.project_path,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "message_count": self.message_count,
            "title": self.title,
            "model": self.model,
            "source_file": self.source_file,
            "parent_session_id": self.parent_session_id,
            "agent": self.agent,
        }


def session_key(engine: str, session_id: str) -> str:
    """逻辑会话主键：``<engine>:<session_id>``。"""
    return f"{engine}:{session_id}"


class SessionIndex:
    """会话索引的读写门面。线程安全，单进程单实例即可。"""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        # 服务进程与 CLI 可能同时写：让 SQLite 自己排一会儿队，而不是立刻
        # 抛 database is locked。
        self._connection.execute("PRAGMA busy_timeout=5000")
        # 派生索引，不值当为每次提交 fsync：首次全量构建有近千个会话事务，
        # NORMAL 能把构建时间砍掉一大截，代价只是断电时可能丢最后一次写入
        # ——而那本来就能从引擎文件重新同步出来。
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._closed = False
        self._migrate()

    @property
    def closed(self) -> bool:
        """后台同步线程据此在索引被关闭后安静退出，而不是往关闭的连接上写。"""
        return self._closed

    def is_ready(self) -> bool:
        """索引是否已经完整地同步过至少一次。"""
        return self.get_meta(LAST_SYNC_KEY) is not None

    # ------------------------------------------------------------------
    # 建表与迁移
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
            )
            row = self._connection.execute(
                "SELECT version FROM schema_version LIMIT 1"
            ).fetchone()
            version = int(row["version"]) if row else 0
            if version > SCHEMA_VERSION:
                # 与 AgentStore 不同：派生索引遇到"更新的 schema"不该把服务拦
                # 下来，重建一份即可。调用方通过异常走回退。
                raise RuntimeError(
                    f"session index schema {version} is newer than supported "
                    f"{SCHEMA_VERSION}"
                )
            if version < 1:
                self._connection.executescript(
                    """
                    CREATE TABLE index_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE sources (
                        source_key TEXT PRIMARY KEY,
                        engine TEXT NOT NULL,
                        source_file TEXT NOT NULL,
                        version_token TEXT NOT NULL,
                        session_key TEXT NOT NULL DEFAULT '',
                        parsed_at TEXT NOT NULL DEFAULT ''
                    );
                    CREATE INDEX sources_engine_idx ON sources(engine);
                    CREATE INDEX sources_session_idx ON sources(session_key);

                    CREATE TABLE sessions (
                        session_key TEXT PRIMARY KEY,
                        engine TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        project_path TEXT NOT NULL DEFAULT '',
                        project_norm TEXT NOT NULL DEFAULT '',
                        started_at TEXT NOT NULL DEFAULT '',
                        ended_at TEXT NOT NULL DEFAULT '',
                        last_activity TEXT NOT NULL DEFAULT '',
                        last_activity_ts INTEGER,
                        message_count INTEGER NOT NULL DEFAULT 0,
                        title TEXT NOT NULL DEFAULT '',
                        raw_title TEXT NOT NULL DEFAULT '',
                        title_fallback TEXT NOT NULL DEFAULT '',
                        model TEXT NOT NULL DEFAULT '',
                        source_file TEXT NOT NULL DEFAULT '',
                        parent_session_id TEXT NOT NULL DEFAULT '',
                        agent TEXT NOT NULL DEFAULT '',
                        is_subagent INTEGER NOT NULL DEFAULT 0,
                        subagent_titles_json TEXT NOT NULL DEFAULT '{}'
                    );
                    CREATE INDEX sessions_activity_idx
                        ON sessions(started_at DESC, session_key);
                    CREATE INDEX sessions_engine_activity_idx
                        ON sessions(engine, started_at DESC);
                    CREATE INDEX sessions_project_activity_idx
                        ON sessions(project_norm, started_at DESC);
                    CREATE INDEX sessions_parent_idx
                        ON sessions(parent_session_id);
                    CREATE INDEX sessions_identity_idx
                        ON sessions(engine, session_id);

                    CREATE TABLE messages (
                        session_key TEXT NOT NULL,
                        ordinal INTEGER NOT NULL,
                        role TEXT NOT NULL DEFAULT '',
                        content TEXT NOT NULL DEFAULT '',
                        timestamp TEXT NOT NULL DEFAULT '',
                        timestamp_ts INTEGER,
                        model TEXT NOT NULL DEFAULT '',
                        has_content INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY(session_key, ordinal),
                        FOREIGN KEY(session_key) REFERENCES sessions(session_key)
                            ON DELETE CASCADE
                    );
                    CREATE INDEX messages_ts_idx ON messages(timestamp DESC);

                    CREATE TABLE tool_calls (
                        session_key TEXT NOT NULL,
                        message_ordinal INTEGER NOT NULL,
                        ordinal INTEGER NOT NULL,
                        name TEXT NOT NULL DEFAULT '',
                        args_preview TEXT NOT NULL DEFAULT '',
                        result_preview TEXT NOT NULL DEFAULT '',
                        timestamp TEXT NOT NULL DEFAULT '',
                        timestamp_ts INTEGER,
                        role TEXT NOT NULL DEFAULT '',
                        model TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY(session_key, message_ordinal, ordinal),
                        FOREIGN KEY(session_key) REFERENCES sessions(session_key)
                            ON DELETE CASCADE
                    );
                    CREATE INDEX tool_calls_ts_idx ON tool_calls(timestamp DESC);
                    CREATE INDEX tool_calls_name_idx ON tool_calls(name);
                    """
                )
                if row:
                    self._connection.execute(
                        "UPDATE schema_version SET version = ?", (SCHEMA_VERSION,)
                    )
                else:
                    self._connection.execute(
                        "INSERT INTO schema_version(version) VALUES (?)",
                        (SCHEMA_VERSION,),
                    )

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._connection.close()

    # ------------------------------------------------------------------
    # index_meta
    # ------------------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM index_meta WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO index_meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # ------------------------------------------------------------------
    # sources（增量摄取的书签）
    # ------------------------------------------------------------------

    def source_versions(self, engine: str) -> dict[str, str]:
        """该引擎已入库的 ``source_key -> version_token``。"""
        with self._lock:
            rows = self._connection.execute(
                "SELECT source_key, version_token FROM sources WHERE engine = ?",
                (engine,),
            ).fetchall()
        return {str(r["source_key"]): str(r["version_token"]) for r in rows}

    def upsert_source(self, ref: SourceRef) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO sources(source_key, engine, source_file, version_token, "
                "session_key, parsed_at) VALUES(?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source_key) DO UPDATE SET "
                "engine = excluded.engine, source_file = excluded.source_file, "
                "version_token = excluded.version_token, "
                "session_key = excluded.session_key, parsed_at = excluded.parsed_at",
                (
                    ref.source_key,
                    ref.engine,
                    ref.source_file,
                    ref.version_token,
                    ref.session_key,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def remove_source(self, source_key: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM sources WHERE source_key = ?", (source_key,)
            )

    def session_key_for_source(self, source_key: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT session_key FROM sources WHERE source_key = ?", (source_key,)
            ).fetchone()
        if row is None:
            return None
        return str(row["session_key"]) or None

    def sources_for_session(self, session_key: str) -> list[str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT source_key FROM sources WHERE session_key = ?",
                (session_key,),
            ).fetchall()
        return [str(r["source_key"]) for r in rows]

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def write_session(self, session: UnifiedSession) -> str:
        """整体替换一个逻辑会话的 sessions/messages/tool_calls 行。

        调用方负责先在 ``sources`` 里登记来源。返回 session_key。
        """
        key = session_key(session.engine.value, session.session_id)
        project_path = session.project_path or ""
        last_activity = session.ended_at or session.started_at or ""
        # raw_title 与 title_fallback 分开存：子代理标题对账要能判断"引擎自己给了
        # 标题没有"，而展示用的 title 是"父给出的一行描述 > 引擎标题 > 首条用户
        # 消息"，与 to_summary_dict() 完全一致。
        raw_title = session.title or ""
        title_fallback = session.first_user_message
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM sessions WHERE session_key = ?", (key,)
            )
            self._connection.execute(
                "INSERT INTO sessions(session_key, engine, session_id, project_path, "
                "project_norm, started_at, ended_at, last_activity, last_activity_ts, "
                "message_count, title, raw_title, title_fallback, model, source_file, "
                "parent_session_id, agent, is_subagent, subagent_titles_json) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key,
                    session.engine.value,
                    session.session_id,
                    project_path,
                    normalize_project_path(project_path),
                    session.started_at or "",
                    session.ended_at or "",
                    last_activity,
                    to_epoch(last_activity),
                    len(session.messages),
                    raw_title or title_fallback,
                    raw_title,
                    title_fallback,
                    session.model or "",
                    session.source_file or "",
                    session.parent_session_id or "",
                    session.agent or "",
                    1 if session.parent_session_id else 0,
                    json.dumps(session.subagent_titles, ensure_ascii=False),
                ),
            )
            self._insert_messages(key, session.messages)
        return key

    def _insert_messages(self, key: str, messages: list[UnifiedMessage]) -> None:
        """调用方须已持有锁与事务。"""
        message_rows: list[tuple[Any, ...]] = []
        tool_rows: list[tuple[Any, ...]] = []
        for ordinal, message in enumerate(messages):
            ts = message.timestamp or ""
            message_rows.append(
                (
                    key,
                    ordinal,
                    message.role or "",
                    message.content or "",
                    ts,
                    to_epoch(ts),
                    message.model or "",
                    1 if (message.content or "").strip() else 0,
                )
            )
            for call_ordinal, call in enumerate(message.tool_calls):
                tool_rows.append(
                    (
                        key,
                        ordinal,
                        call_ordinal,
                        call.name or "",
                        call.args_preview or "",
                        call.result_preview or "",
                        ts,
                        to_epoch(ts),
                        message.role or "",
                        message.model or "",
                    )
                )
        if message_rows:
            self._connection.executemany(
                "INSERT INTO messages(session_key, ordinal, role, content, timestamp, "
                "timestamp_ts, model, has_content) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                message_rows,
            )
        if tool_rows:
            self._connection.executemany(
                "INSERT INTO tool_calls(session_key, message_ordinal, ordinal, name, "
                "args_preview, result_preview, timestamp, timestamp_ts, role, model) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tool_rows,
            )

    def delete_session(self, key: str) -> None:
        """删逻辑会话（级联清掉消息与工具调用）。不动 ``sources``。"""
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM sessions WHERE session_key = ?", (key,)
            )

    def set_session_parent(self, key: str, parent_session_id: str, agent: str) -> None:
        """只更新父子/代理信息（codex lineage、antigravity 元数据用）。"""
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE sessions SET parent_session_id = ?, agent = ?, is_subagent = ? "
                "WHERE session_key = ?",
                (parent_session_id, agent, 1 if parent_session_id else 0, key),
            )

    def set_session_project(self, key: str, project_path: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE sessions SET project_path = ?, project_norm = ? "
                "WHERE session_key = ?",
                (project_path, normalize_project_path(project_path), key),
            )

    def set_session_title(self, key: str, title: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE sessions SET title = ? WHERE session_key = ?", (title, key)
            )

    def unresolved_subagents(self) -> list[tuple[str, str, str, str, str]]:
        """等待父会话给出标题的子代理行。

        判定条件是"引擎没给标题"（raw_title 为空）且"标题还没被父覆盖过"
        （title 仍等于 fallback）。
        """
        with self._lock:
            rows = self._connection.execute(
                "SELECT session_key, engine, session_id, parent_session_id, "
                "title_fallback FROM sessions "
                "WHERE parent_session_id != '' AND raw_title = '' "
                "AND title = title_fallback"
            ).fetchall()
        return [
            (
                str(r["session_key"]),
                str(r["engine"]),
                str(r["session_id"]),
                str(r["parent_session_id"]),
                str(r["title_fallback"]),
            )
            for r in rows
        ]

    def get_subagent_titles_json(self, parent_key: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT subagent_titles_json FROM sessions WHERE session_key = ?",
                (parent_key,),
            ).fetchone()
        return str(row["subagent_titles_json"]) if row else None

    def reset_children_titles(self, engine: str, parent_session_id: str) -> None:
        """父会话重解析后，把它名下"引擎没给标题"的子代理标题打回 fallback。

        否则父的启动描述改了，已经解析过的子标题不会跟着更新。
        """
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE sessions SET title = title_fallback "
                "WHERE engine = ? AND parent_session_id = ? AND raw_title = ''",
                (engine, parent_session_id),
            )

    def inherit_parent_projects(self, engine: str) -> int:
        """把项目路径为空的子会话从父会话继承过来，返回改动行数。

        父可能比子晚入库，调用方循环到返回 0 为止（有界）。
        """
        # 父主键 = 同引擎 + 父 session_id。
        parent_key = "sessions.engine || ':' || sessions.parent_session_id"
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE sessions SET "
                "project_path = (SELECT p.project_path FROM sessions p "
                f"WHERE p.session_key = {parent_key}), "
                "project_norm = (SELECT p.project_norm FROM sessions p "
                f"WHERE p.session_key = {parent_key}) "
                "WHERE engine = ? AND project_path = '' AND parent_session_id != '' "
                "AND EXISTS (SELECT 1 FROM sessions p "
                f"WHERE p.session_key = {parent_key} AND p.project_path != '')",
                (engine,),
            )
        return int(cursor.rowcount or 0)

    def delete_orphan_sessions(self) -> int:
        """删掉没有任何来源指向的会话行（来源被删/改了 id 之后的残留）。"""
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM sessions WHERE session_key NOT IN ("
                "  SELECT session_key FROM sources WHERE session_key != ''"
                ")"
            )
        return int(cursor.rowcount or 0)

    def clear_all(self) -> None:
        """清空全部派生数据，用于 parser 指纹变化后的全量重建。"""
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM tool_calls")
            self._connection.execute("DELETE FROM messages")
            self._connection.execute("DELETE FROM sessions")
            self._connection.execute("DELETE FROM sources")

    def session_count(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS n FROM sessions"
            ).fetchone()
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def list_summaries(
        self,
        *,
        project: str | None = None,
        engine: str | None = None,
        include_subagents: bool = False,
        limit: int = 500,
    ) -> list[SessionSummary]:
        """按 ``started_at`` 倒序返回摘要行，过滤/排序/LIMIT 全部下推。"""
        clauses: list[str] = []
        params: list[Any] = []
        if not include_subagents:
            clauses.append("parent_session_id = ''")
        if engine:
            clauses.append("engine = ?")
            params.append(engine)
        if project:
            clauses.append("project_norm = ?")
            params.append(normalize_project_path(project))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, limit))
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM sessions {where} "
                "ORDER BY started_at DESC, session_key DESC LIMIT ?",
                params,
            ).fetchall()
        return [_row_to_summary(r) for r in rows]

    def get_summary(self, engine: str, session_id: str) -> SessionSummary | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE engine = ? AND session_id = ?",
                (engine, session_id),
            ).fetchone()
        return _row_to_summary(row) if row else None

    def get_title_map(self) -> dict[tuple[str, str], str]:
        """``(engine, session_id) -> 已解析标题``，替代每请求重建的 title 表。"""
        with self._lock:
            rows = self._connection.execute(
                "SELECT engine, session_id, title FROM sessions"
            ).fetchall()
        return {(str(r["engine"]), str(r["session_id"])): str(r["title"]) for r in rows}

    def reconstruct(self, engine: str, session_id: str) -> UnifiedSession | None:
        """由索引行还原完整 ``UnifiedSession``（详情/转换用）。"""
        summary = self.get_summary(engine, session_id)
        if summary is None:
            return None
        key = summary.session_key
        with self._lock:
            message_rows = self._connection.execute(
                "SELECT * FROM messages WHERE session_key = ? ORDER BY ordinal",
                (key,),
            ).fetchall()
            tool_rows = self._connection.execute(
                "SELECT * FROM tool_calls WHERE session_key = ? "
                "ORDER BY message_ordinal, ordinal",
                (key,),
            ).fetchall()
            titles_row = self._connection.execute(
                "SELECT subagent_titles_json FROM sessions WHERE session_key = ?",
                (key,),
            ).fetchone()

        by_message: dict[int, list[ToolCallSummary]] = {}
        for r in tool_rows:
            by_message.setdefault(int(r["message_ordinal"]), []).append(
                ToolCallSummary(
                    name=str(r["name"]),
                    args_preview=str(r["args_preview"]),
                    result_preview=str(r["result_preview"]),
                )
            )
        messages = [
            UnifiedMessage(
                role=str(r["role"]),
                content=str(r["content"]),
                timestamp=str(r["timestamp"]),
                tool_calls=by_message.get(int(r["ordinal"]), []),
                model=str(r["model"]),
            )
            for r in message_rows
        ]
        try:
            subagent_titles = (
                json.loads(titles_row["subagent_titles_json"]) if titles_row else {}
            )
        except (TypeError, ValueError):
            subagent_titles = {}
        return UnifiedSession(
            session_id=summary.session_id,
            engine=EngineType(summary.engine),
            project_path=summary.project_path,
            started_at=summary.started_at,
            ended_at=summary.ended_at,
            messages=messages,
            title=summary.title,
            model=summary.model,
            source_file=summary.source_file,
            parent_session_id=summary.parent_session_id,
            agent=summary.agent,
            subagent_titles=subagent_titles,
        )

    def audit_events(
        self,
        *,
        engine: str | None = None,
        project: str | None = None,
        since: int | None = None,
        until: int | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """跨会话的事件时间线，``LIMIT`` 下推到 SQL。

        事件的 ``event_id`` / 键与 ``core.session_history.audit`` 保持一致：
        消息一个事件、每个工具调用一个事件。
        """
        params: list[Any] = []
        filters = ""
        if engine:
            filters += " AND q.engine = ?"
            params.append(engine)
        if project:
            filters += " AND q.project_norm = ?"
            params.append(normalize_project_path(project))
        if since is not None:
            filters += " AND q.timestamp_ts IS NOT NULL AND q.timestamp_ts >= ?"
            params.append(since)
        if until is not None:
            filters += " AND q.timestamp_ts IS NOT NULL AND q.timestamp_ts <= ?"
            params.append(until)

        sql = f"""
            SELECT * FROM (
                SELECT s.engine || ':' || s.session_id || ':' || m.ordinal AS event_id,
                       'message' AS event_type, s.engine AS engine,
                       s.project_norm AS project_norm,
                       s.project_path AS project_path, s.session_id AS session_id,
                       s.title AS session_title, m.timestamp AS timestamp,
                       m.role AS role, m.model AS model, m.content AS content_preview,
                       NULL AS tool_name, NULL AS args_preview,
                       NULL AS result_preview, m.timestamp_ts AS timestamp_ts
                FROM messages m JOIN sessions s ON s.session_key = m.session_key
                WHERE m.has_content = 1
                UNION ALL
                SELECT s.engine || ':' || s.session_id || ':' || t.message_ordinal
                           || ':' || t.ordinal,
                       'tool_call', s.engine, s.project_norm, s.project_path,
                       s.session_id, s.title,
                       t.timestamp, t.role, t.model, NULL, t.name, t.args_preview,
                       t.result_preview, t.timestamp_ts
                FROM tool_calls t JOIN sessions s ON s.session_key = t.session_key
                WHERE 1 = 1
            ) q
            WHERE 1 = 1 {filters}
            ORDER BY q.timestamp DESC, q.event_id DESC
            LIMIT ?
        """
        params.append(max(1, min(limit, _MAX_AUDIT_LIMIT)))
        with self._lock:
            rows = self._connection.execute(sql, params).fetchall()
        return [_row_to_audit_event(r) for r in rows]

    def tool_usage(
        self,
        *,
        project: str | None = None,
        engine: str | None = None,
        since: int | None = None,
    ) -> dict[str, Any]:
        """工具调用排行，``GROUP BY`` 在 SQL 里做。"""
        clauses: list[str] = []
        params: list[Any] = []
        if engine:
            clauses.append("s.engine = ?")
            params.append(engine)
        if project:
            clauses.append("s.project_norm = ?")
            params.append(normalize_project_path(project))
        if since is not None:
            clauses.append("s.last_activity_ts IS NOT NULL AND s.last_activity_ts >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._lock:
            rows = self._connection.execute(
                f"SELECT t.name AS name, s.engine AS engine, COUNT(*) AS n "
                f"FROM tool_calls t JOIN sessions s ON s.session_key = t.session_key "
                f"{where} GROUP BY t.name, s.engine",
                params,
            ).fetchall()
            session_row = self._connection.execute(
                f"SELECT COUNT(*) AS n FROM sessions s {where}",
                params,
            ).fetchone()

        totals: dict[str, int] = {}
        per_engine: dict[str, dict[str, int]] = {}
        engines: dict[str, int] = {}
        for r in rows:
            name = str(r["name"])
            count = int(r["n"])
            totals[name] = totals.get(name, 0) + count
            per_engine.setdefault(name, {})[str(r["engine"])] = count
            engines[str(r["engine"])] = engines.get(str(r["engine"]), 0) + count
        ordered = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
        return {
            "tools": [
                {
                    "name": name,
                    "count": count,
                    "byEngine": dict(
                        sorted(
                            per_engine[name].items(),
                            key=lambda kv: (-kv[1], kv[0]),
                        )
                    ),
                }
                for name, count in ordered
            ],
            "totalCalls": sum(totals.values()),
            "sessions": int(session_row["n"]) if session_row else 0,
            "engines": dict(sorted(engines.items(), key=lambda kv: (-kv[1], kv[0]))),
        }


def _row_to_summary(row: sqlite3.Row) -> SessionSummary:
    return SessionSummary(
        session_key=str(row["session_key"]),
        engine=str(row["engine"]),
        session_id=str(row["session_id"]),
        project_path=str(row["project_path"]),
        project_norm=str(row["project_norm"]),
        started_at=str(row["started_at"]),
        ended_at=str(row["ended_at"]),
        last_activity=str(row["last_activity"]),
        message_count=int(row["message_count"]),
        title=str(row["title"]),
        model=str(row["model"]),
        source_file=str(row["source_file"]),
        parent_session_id=str(row["parent_session_id"]),
        agent=str(row["agent"]),
    )


def _row_to_audit_event(row: sqlite3.Row) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_id": str(row["event_id"]),
        "event_type": str(row["event_type"]),
        "engine": str(row["engine"]),
        "project_path": str(row["project_path"]),
        "session_id": str(row["session_id"]),
        "session_title": str(row["session_title"]),
        "timestamp": str(row["timestamp"]),
        "role": str(row["role"]),
        "model": str(row["model"]),
    }
    if event["event_type"] == "message":
        event["content_preview"] = str(row["content_preview"] or "")
    else:
        event["tool_name"] = str(row["tool_name"] or "")
        event["args_preview"] = str(row["args_preview"] or "")
        event["result_preview"] = str(row["result_preview"] or "")
    return event


# ----------------------------------------------------------------------
# 进程内单例
# ----------------------------------------------------------------------

_index: SessionIndex | None = None
_index_lock = threading.Lock()
_index_broken = False


def get_index() -> SessionIndex | None:
    """返回进程内的索引实例；关闭或打不开时返回 None，调用方回退 finder。

    派生索引不值得让整个服务起不来：损坏就标记坏掉、走回退，下次进程重启
    会重新尝试建库。
    """
    global _index, _index_broken
    if index_disabled():
        return None
    with _index_lock:
        if _index is not None:
            return _index
        if _index_broken:
            return None
        path = os.environ.get(ENV_PATH) or None
        try:
            _index = SessionIndex(path or default_index_path())
        except (sqlite3.DatabaseError, RuntimeError, OSError):
            logger.warning(
                "Session index unavailable; falling back to on-demand parsing",
                exc_info=True,
            )
            _index_broken = True
            return None
        return _index


def reset_index_for_tests() -> None:
    """丢掉单例，供测试在换 HOME/换路径后重新获取。"""
    global _index, _index_broken
    with _index_lock:
        if _index is not None:
            try:
                _index.close()
            except sqlite3.Error:
                pass
        _index = None
        _index_broken = False
