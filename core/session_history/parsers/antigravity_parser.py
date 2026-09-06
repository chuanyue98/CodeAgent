"""Parser for Antigravity session history files.

Antigravity stores sessions as JSONL at:
    ~/.gemini/antigravity-cli/brain/<session_id>/.system_generated/logs/transcript.jsonl

And metadata at:
    ~/.gemini/antigravity-cli/conversation_summaries.db

Each line of transcript.jsonl is a JSON object with a ``type`` field. Relevant types:
  - ``USER_INPUT``       → user messages (wraps content in <USER_REQUEST>...</USER_REQUEST>)
  - ``PLANNER_RESPONSE`` → assistant replies (text content and tool_calls list)
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)
from core.session_history.parse_cache import cached_file_parser
from core.session_history.parsers._subagents import title_subagent_runs
from core.session_history.paths import (
    normalize_project_path,
    strip_extended_length_prefix,
)
from core.utils.long_paths import exists as path_exists
from core.utils.long_paths import list_dirs, long_path

_USER_REQUEST_RE = re.compile(r"<USER_REQUEST>(.*?)</USER_REQUEST>", re.DOTALL)


def _is_valid_project_path(path_str: str) -> bool:
    if not path_str:
        return False
    p = path_str.strip("\"' ")
    if not (p.startswith("/") or (len(p) > 2 and p[1] == ":")):
        return False
    if "/.gemini/" in p or p.endswith("/.gemini") or p.startswith("/tmp"):
        return False
    return True


def _find_repo_root(path_str: str) -> str:
    try:
        curr = Path(path_str)
        if not curr.is_dir():
            curr = curr.parent
        for _ in range(len(curr.parts)):
            if (
                (curr / ".git").exists()
                or (curr / "pyproject.toml").exists()
                or (curr / "package.json").exists()
            ):
                return str(curr)
            if curr.parent == curr:
                break
            curr = curr.parent
    except Exception:
        pass
    return path_str


def _clean_title(content: str) -> str:
    """Derives a concise, clean human-readable title from user content."""
    m = _USER_REQUEST_RE.search(content)
    text = m.group(1).strip() if m else content.strip()
    role_m = re.search(r"^\s*你是\s*(.+?)[。，：:\n]", text)
    if role_m:
        return role_m.group(1).strip()
    first_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if first_lines:
        clean = first_lines[0]
        clean = re.sub(r"^([#*->\d.]+\s*)+", "", clean).strip()
        return clean[:80]
    return ""


def _uri_to_path(uri: str) -> str:
    """Converts a file:// URI to a local filesystem path."""
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        path = unquote(parsed.path)
        # On Windows, file:///C:/path -> /C:/path
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return strip_extended_length_prefix(path.replace("\\", "/"))
    return strip_extended_length_prefix(uri.replace("\\", "/"))


def _extract_session_id(file_path: Path) -> str:
    """Extracts session ID from the transcript file path."""
    parts = file_path.parts
    if ".system_generated" in parts:
        idx = parts.index(".system_generated")
        if idx > 0:
            return parts[idx - 1]
    if "brain" in parts:
        idx = parts.index("brain")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    if file_path.name == "transcript.jsonl":
        return file_path.parent.name
    return file_path.stem


def _normalize_model_name(raw: str) -> str:
    """Normalizes raw model name or descriptor string to a standard identifier."""
    s = raw.lower().strip()
    if "3.8" in s and "flash" in s:
        return "gemini-3.8-flash"
    if "3.6" in s and "flash" in s:
        return "gemini-3.6-flash"
    if "3" in s and "pro" in s:
        return "gemini-3-pro"
    if "2.5" in s and "pro" in s:
        return "gemini-2.5-pro"
    if "2.5" in s and "flash" in s:
        return "gemini-2.5-flash"
    if "2.0" in s and "flash" in s:
        return "gemini-2.0-flash"
    if s.startswith("gemini-"):
        return s
    return raw.strip()


def _read_configured_model(file_path: Path) -> str:
    """Reads configured model from nearby settings.json or user home."""
    try:
        curr = file_path.resolve()
        for _ in range(len(curr.parts)):
            settings = curr / "settings.json"
            if path_exists(settings):
                try:
                    with open(long_path(settings), encoding="utf-8") as f:
                        data = json.load(f)
                        m = data.get("model")
                        if m:
                            return _normalize_model_name(str(m))
                except (OSError, json.JSONDecodeError):
                    pass
            if curr.name == "antigravity-cli":
                break
            if curr.parent == curr:
                break
            curr = curr.parent
    except Exception:
        pass

    home_settings = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
    if path_exists(home_settings):
        try:
            with open(long_path(home_settings), encoding="utf-8") as f:
                data = json.load(f)
                m = data.get("model")
                if m:
                    return _normalize_model_name(str(m))
        except (OSError, json.JSONDecodeError):
            pass

    return "gemini-3.8-flash"


def _find_summaries_db(file_path: Path, home: Path | None = None) -> Path | None:
    """Locates conversation_summaries.db near file_path or in home."""
    curr = file_path.resolve()
    for parent in curr.parents:
        candidate = parent / "conversation_summaries.db"
        if path_exists(candidate):
            return candidate
        if parent.name == "brain" and path_exists(
            parent.parent / "conversation_summaries.db"
        ):
            return parent.parent / "conversation_summaries.db"

    base_dir = (home or Path.home()) / ".gemini" / "antigravity-cli"
    candidate = base_dir / "conversation_summaries.db"
    if path_exists(candidate):
        return candidate
    return None


def _get_metadata_from_db(db_path: Path, session_id: str) -> dict[str, str]:
    """Queries conversation_summaries.db for session metadata."""
    res = {
        "title": "",
        "project_path": "",
        "parent_session_id": "",
        "agent": "",
    }
    try:
        with sqlite3.connect(f"file:{long_path(db_path)}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT title, preview, workspace_uris, parent_conversation_id, agent_name "
                "FROM conversation_summaries WHERE conversation_id = ?",
                (session_id,),
            ).fetchone()
            if row:
                title = row["title"] or row["preview"] or ""
                res["title"] = title
                res["parent_session_id"] = row["parent_conversation_id"] or ""
                res["agent"] = row["agent_name"] or ""
                uris_str = row["workspace_uris"] or ""
                if uris_str:
                    try:
                        uris = json.loads(uris_str)
                        if isinstance(uris, list):
                            for uri in uris:
                                if isinstance(uri, str) and uri.startswith("file://"):
                                    res["project_path"] = _uri_to_path(uri)
                                    break
                    except (json.JSONDecodeError, TypeError):
                        pass
    except (sqlite3.Error, OSError):
        pass
    return res


def _extract_tool_calls(tool_calls_raw: list) -> list[ToolCallSummary]:
    """Converts Antigravity raw tool calls to ToolCallSummary objects."""
    tool_calls: list[ToolCallSummary] = []
    for tc in tool_calls_raw:
        if not isinstance(tc, dict):
            continue
        name = str(tc.get("name") or "")
        args = tc.get("args")
        if isinstance(args, (dict, list)):
            args_preview = json.dumps(args, ensure_ascii=False)
        elif args is not None:
            args_preview = str(args)
        else:
            args_preview = ""
        if len(args_preview) > 200:
            args_preview = args_preview[:200] + "..."
        tool_calls.append(ToolCallSummary(name=name, args_preview=args_preview))
    return tool_calls


def _extract_user_content(content: str) -> str:
    """Extracts user content, preferring content inside <USER_REQUEST> tags."""
    m = _USER_REQUEST_RE.search(content)
    if m:
        return m.group(1).strip()
    return content.strip()


@cached_file_parser
def parse_antigravity_session(file_path: Path) -> UnifiedSession | None:
    """Parses an Antigravity transcript.jsonl file into a UnifiedSession.

    Args:
        file_path: Path to the transcript.jsonl file.

    Returns:
        UnifiedSession if parsing succeeds, None otherwise.
    """
    if not path_exists(file_path) or file_path.name != "transcript.jsonl":
        return None

    session_id = _extract_session_id(file_path)
    if not session_id:
        return None

    db_path = _find_summaries_db(file_path)
    meta = _get_metadata_from_db(db_path, session_id) if db_path else {}

    raw_rows: list[dict] = []
    try:
        with open(long_path(file_path), encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        raw_rows.append(row)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return None

    # Sort rows by step_index to ensure chronological sequence
    raw_rows.sort(key=lambda r: r.get("step_index", 0))

    messages: list[UnifiedMessage] = []
    started_at = ""
    ended_at = ""
    model = ""

    inferred_project_path = ""
    computed_title = ""
    subagent_titles: dict[str, str] = {}
    for row in raw_rows:
        row_type = row.get("type", "")
        # 1. Infer project path
        if not inferred_project_path:
            content_str = row.get("content") or ""
            m = re.search(
                r"^\s*(/[^\s\n\r]+|[a-zA-Z]:[/\\][^\s\n\r]+)\s*->", content_str, re.M
            )
            if m and _is_valid_project_path(m.group(1)):
                inferred_project_path = _find_repo_root(m.group(1).strip("\"' "))
            else:
                for tc in row.get("tool_calls") or []:
                    if isinstance(tc, dict):
                        args = tc.get("args")
                        if isinstance(args, dict):
                            cwd = args.get("Cwd")
                            if (
                                cwd
                                and isinstance(cwd, str)
                                and _is_valid_project_path(cwd)
                            ):
                                inferred_project_path = _find_repo_root(
                                    cwd.strip("\"' ")
                                )
                                break
                            for k in (
                                "SearchDirectory",
                                "DirectoryPath",
                                "SearchPath",
                                "TargetFile",
                                "AbsolutePath",
                            ):
                                raw_val = args.get(k)
                                if (
                                    raw_val
                                    and isinstance(raw_val, str)
                                    and _is_valid_project_path(raw_val)
                                ):
                                    cand = raw_val.strip("\"' ")
                                    inferred_project_path = _find_repo_root(cand)
                                    break
                        if inferred_project_path:
                            break

        # 2. Collect subagent titles from invoke_subagent tool calls
        for tc in row.get("tool_calls") or []:
            if isinstance(tc, dict) and tc.get("name") == "invoke_subagent":
                args = tc.get("args") or {}
                subs = args.get("Subagents")
                if isinstance(subs, str):
                    try:
                        subs = json.loads(subs)
                    except (json.JSONDecodeError, TypeError):
                        pass
                if isinstance(subs, list):
                    curr_step = row.get("step_index", 0)
                    for r2 in raw_rows:
                        if r2.get("step_index", 0) > curr_step:
                            c2 = r2.get("content") or ""
                            if "conversationId" in c2:
                                cids = re.findall(r'"conversationId":\s*"([^"]+)"', c2)
                                for idx, cid in enumerate(cids):
                                    if idx < len(subs) and isinstance(subs[idx], dict):
                                        role = subs[idx].get("Role") or subs[idx].get(
                                            "TypeName"
                                        )
                                        if role:
                                            subagent_titles[cid] = role
                                break

        # 3. Extract model information if present
        if not model:
            raw_model = row.get("model") or row.get("modelTier")
            if isinstance(raw_model, str) and raw_model:
                model = _normalize_model_name(raw_model)
            else:
                c_text = row.get("content") or ""
                m_match = re.search(
                    r"(?:Model Selection`?\s+from.*?to|model(?:_name)?\s*[:=])\s*([a-zA-Z0-9\.\-\_\s]+)",
                    c_text,
                    re.IGNORECASE,
                )
                if m_match:
                    model = _normalize_model_name(m_match.group(1).strip("`'\" ()"))

        if row_type not in ("USER_INPUT", "PLANNER_RESPONSE"):
            continue

        ts = row.get("created_at") or ""
        if not started_at and ts:
            started_at = ts
        if ts:
            ended_at = ts

        if row_type == "USER_INPUT":
            raw_content = row.get("content") or ""
            if not computed_title:
                computed_title = _clean_title(raw_content)
            content = _extract_user_content(raw_content)
            if content:
                messages.append(
                    UnifiedMessage(
                        role="user",
                        content=content,
                        timestamp=ts,
                    )
                )
        elif row_type == "PLANNER_RESPONSE":
            content = (row.get("content") or "").strip()
            tool_calls_raw = row.get("tool_calls") or []
            tool_calls = (
                _extract_tool_calls(tool_calls_raw)
                if isinstance(tool_calls_raw, list)
                else []
            )
            if content or tool_calls:
                messages.append(
                    UnifiedMessage(
                        role="assistant",
                        content=content,
                        timestamp=ts,
                        tool_calls=tool_calls,
                        model=model,
                    )
                )

    if not messages:
        return None

    if not model:
        model = _read_configured_model(file_path)

    for msg in messages:
        if msg.role == "assistant" and not msg.model:
            msg.model = model

    resolved_project_path = meta.get("project_path", "") or inferred_project_path
    resolved_title = meta.get("title", "") or computed_title

    return UnifiedSession(
        session_id=session_id,
        engine=EngineType.ANTIGRAVITY,
        project_path=resolved_project_path,
        started_at=started_at,
        ended_at=ended_at,
        messages=messages,
        title=resolved_title,
        model=model,
        source_file=str(file_path),
        parent_session_id=meta.get("parent_session_id", ""),
        agent=meta.get("agent", ""),
        subagent_titles=subagent_titles,
    )


def find_antigravity_sessions(
    project_path: str | None = None, home: Path | None = None
) -> list[UnifiedSession]:
    """Finds all Antigravity sessions matching project_path.

    Args:
        project_path: Directory path to match against. If None, returns all.
        home: Optional home directory override.

    Returns:
        list[UnifiedSession]: Matching sessions sorted by started_at descending.
    """
    base_dir = (home or Path.home()) / ".gemini" / "antigravity-cli"
    if not base_dir.exists():
        return []

    normalized_target = (
        normalize_project_path(project_path) if project_path is not None else None
    )

    db_path = base_dir / "conversation_summaries.db"
    brain_dir = base_dir / "brain"

    sessions: list[UnifiedSession] = []
    seen_ids: set[str] = set()

    # 1. Try reading from conversation_summaries.db first
    if db_path.is_file():
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT conversation_id, workspace_uris, title, preview, "
                    "parent_conversation_id, agent_name FROM conversation_summaries"
                ).fetchall()
                for row in rows:
                    sess_id = row["conversation_id"]
                    if not sess_id:
                        continue
                    sess_project = ""
                    uris_str = row["workspace_uris"] or ""
                    if uris_str:
                        try:
                            uris = json.loads(uris_str)
                            if isinstance(uris, list):
                                for uri in uris:
                                    if isinstance(uri, str) and uri.startswith(
                                        "file://"
                                    ):
                                        sess_project = _uri_to_path(uri)
                                        break
                        except (json.JSONDecodeError, TypeError):
                            pass

                    transcript_file = (
                        brain_dir
                        / sess_id
                        / ".system_generated"
                        / "logs"
                        / "transcript.jsonl"
                    )
                    if not transcript_file.is_file():
                        transcript_file = brain_dir / sess_id / "transcript.jsonl"
                    if not transcript_file.is_file():
                        continue

                    session = parse_antigravity_session(transcript_file)
                    if session:
                        if sess_project and not session.project_path:
                            session.project_path = sess_project
                        if not session.title:
                            session.title = row["title"] or row["preview"] or ""
                        sessions.append(session)
                        seen_ids.add(sess_id)
        except (sqlite3.Error, OSError):
            pass

    # 2. Also scan brain_dir for any transcripts not covered by DB
    if brain_dir.is_dir():
        for sess_dir in list_dirs(brain_dir):
            sess_id = sess_dir.name
            if sess_id in seen_ids:
                continue
            transcript_file = (
                sess_dir / ".system_generated" / "logs" / "transcript.jsonl"
            )
            if not transcript_file.is_file():
                transcript_file = sess_dir / "transcript.jsonl"
            if not transcript_file.is_file():
                continue

            session = parse_antigravity_session(transcript_file)
            if not session:
                continue

            sessions.append(session)
            seen_ids.add(sess_id)

    # Inherit project path from parent session when subagent project path is empty
    by_id = {s.session_id: s for s in sessions}
    for s in sessions:
        if not s.project_path and s.parent_session_id:
            parent = by_id.get(s.parent_session_id)
            if parent and parent.project_path:
                s.project_path = parent.project_path

    # Apply subagent titles from parent sessions
    title_subagent_runs(sessions)

    # Filter by project path if requested
    if normalized_target is not None:
        sessions = [
            s
            for s in sessions
            if s.project_path
            and normalize_project_path(s.project_path) == normalized_target
        ]

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions
