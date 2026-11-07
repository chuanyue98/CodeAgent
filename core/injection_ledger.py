"""注入账本：记下 CodeAgent 往引擎配置文件里写了什么，退出时只收回自己写的。

旧做法是注入前把整个文件拷成
``.bak``、退出时整个拷回去：会话期间引擎或用户对这个文件的任何改动（codex
写进 ``~/.codex/config.toml`` 的项目信任、``/model`` 选择，用户在 claude 里改
的 settings）都会在退出时被旧副本覆盖掉。

账本是配置文件旁边的一个 JSON 文件（``<文件名>.codeagent-applied.json``），
记三样东西：

- ``original``：第一次注入前文件的原文（``None`` 表示文件原本不存在）。
- ``written_digest``：最后一次注入写完后文件内容的 sha256。
- ``entries`` / ``created``：注入方自己定义的明细——写了哪些条目、条目原先的值、
  哪些容器是注入时新建的。账本本身不解释它们。

收回时分两种情况：

1. 文件内容的摘要仍等于 ``written_digest``：注入之后没人动过，按 ``original``
   逐字节写回（原本不存在就删掉），格式、注释、换行原样恢复。
2. 摘要变了：有人改过文件。只按 ``entries`` 摘掉自己写的条目，别人的改动保留。

同一文件的多个会话、崩溃后的下一次启动都会在已有账本上合并：``original``
和条目的「原先的值」只在第一次记下，之后不再覆盖。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from core.logging_config import get_logger
from core.utils.atomic_write import atomic_write

logger = get_logger(__name__)

LEDGER_SUFFIX = ".codeagent-applied.json"
LEDGER_VERSION = 1


def ledger_path_for(settings_path: Path) -> Path:
    return settings_path.with_name(settings_path.name + LEDGER_SUFFIX)


def file_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def read_raw_text(path: Path) -> str | None:
    """不做换行转换地读出原文，``None`` 表示文件不存在。"""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()
    except FileNotFoundError:
        return None


class InjectionLedger:
    """一个配置文件的注入账本。"""

    def __init__(self, settings_path: Path):
        self.settings_path = settings_path
        self.path = ledger_path_for(settings_path)
        self.original: str | None = None
        self.written_digest: str | None = None
        self.entries: list[dict[str, Any]] = []
        self.created: list[Any] = []
        self._loaded = False

    # ── 读写 ──────────────────────────────────────────────────────────────

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> bool:
        """读入账本，返回是否存在且可用。损坏的账本按不存在处理并记警告。"""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return False
        except (OSError, ValueError) as exc:
            logger.warning("注入账本 %s 无法读取，按不存在处理: %s", self.path, exc)
            return False
        if not isinstance(data, dict) or data.get("version") != LEDGER_VERSION:
            logger.warning("注入账本 %s 格式不认识，按不存在处理", self.path)
            return False
        original = data.get("original")
        self.original = original if isinstance(original, str) else None
        digest = data.get("written_digest")
        self.written_digest = digest if isinstance(digest, str) else None
        entries = data.get("entries")
        self.entries = (
            [e for e in entries if isinstance(e, dict)]
            if isinstance(entries, list)
            else []
        )
        created = data.get("created")
        self.created = list(created) if isinstance(created, list) else []
        self._loaded = True
        return True

    def save(self) -> None:
        payload = {
            "version": LEDGER_VERSION,
            "file": str(self.settings_path),
            "original": self.original,
            "written_digest": self.written_digest,
            "entries": self.entries,
            "created": self.created,
        }
        atomic_write(
            self.path, json.dumps(payload, indent=2, ensure_ascii=False), fsync=True
        )

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)

    # ── 注入流程 ──────────────────────────────────────────────────────────

    def begin(self) -> None:
        """注入前调用：已有账本就沿用（合并），没有就记下文件此刻的原文。

        账本先于配置文件落盘：即使紧接着崩溃，下一次也知道原文是什么。
        """
        if self._loaded or self.load():
            return
        self.original = read_raw_text(self.settings_path)
        self.written_digest = file_digest(self.settings_path)
        self.entries = []
        self.created = []
        self._loaded = True
        self.save()

    def commit(self) -> None:
        """配置文件写完后调用，记下写完的摘要。"""
        self.written_digest = file_digest(self.settings_path)
        self.save()

    def find_entry(self, **match: Any) -> dict[str, Any] | None:
        return next(
            (e for e in self.entries if all(e.get(k) == v for k, v in match.items())),
            None,
        )

    def note_created(self, marker: Any) -> None:
        if marker not in self.created:
            self.created.append(marker)

    # ── 收回 ──────────────────────────────────────────────────────────────

    def untouched_since_commit(self) -> bool:
        return (
            self.written_digest is not None
            and file_digest(self.settings_path) == self.written_digest
        )

    def restore_original(self) -> None:
        """把文件逐字节恢复成第一次注入前的样子（原本不存在就删掉）。"""
        if self.original is None:
            self.settings_path.unlink(missing_ok=True)
            return
        atomic_write(self.settings_path, self.original, newline="")
