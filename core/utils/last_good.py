"""ca 自己的状态文件：保留上一份完好的副本，文件读不懂时改读它。

原子写（:mod:`core.utils.atomic_write`）挡得住写到一半进程退出，挡不住
Windows 断电：文件系统可能留下长度正确、内容全是 0 的文件。读的一方若把
「读不懂」当成「空」，下一次写入就把损坏变成了定局——账本空了就什么都收不回，
config.json 空了就丢了全部项目组。

做法：

- 每次写入前调用 :func:`keep_last_good`：当前文件完好，就拷成
  ``<文件名>.lastgood``；读不懂，就另存成 ``<文件名>.bad-<时间>`` 留作证据，
  ``.lastgood`` 不动。
- 读的时候用 :func:`read_with_fallback`：文件本身读不懂时返回 ``.lastgood``
  的内容，并带一条说明，交给调用方提示用户。文件不存在不算损坏，不回退。

不用 ``.bak`` 这个名字：旧版整文件注入留下的 ``.bak`` 有自己的含义（见
:meth:`core.settings_manager.SettingsFile.restore_backup`）。
"""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from core.logging_config import get_logger
from core.utils.atomic_write import atomic_write

logger = get_logger(__name__)

LAST_GOOD_SUFFIX = ".lastgood"
BAD_COPY_INFIX = ".bad-"


def last_good_path(path: Path) -> Path:
    return path.with_name(path.name + LAST_GOOD_SUFFIX)


def looks_crash_damaged(raw: bytes) -> bool:
    """空文件或全是 0 字节：断电留下的样子，不会是谁手改出来的。"""
    return raw.strip(b"\x00 \t\r\n") == b""


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _parse[T](raw: bytes, parse: Callable[[str], T]) -> T:
    return parse(raw.decode("utf-8-sig"))


def keep_last_good(path: Path, parse: Callable[[str], object]) -> None:
    """写入 *path* 之前调用：完好就存一份，读不懂就另存成坏副本。

    *parse* 读不懂时应抛异常。这里任何失败都只记警告：保存副本是额外的
    保险，不能因此挡住真正的写入。
    """
    raw = _read_bytes(path)
    if raw is None:
        return
    try:
        _parse(raw, parse)
    except Exception:
        bad = path.with_name(f"{path.name}{BAD_COPY_INFIX}{time.time_ns()}")
        try:
            shutil.copyfile(path, bad)
            logger.warning("%s 读不懂，覆盖前另存为 %s", path, bad)
        except OSError as exc:
            logger.warning("%s 读不懂，另存失败: %s", path, exc)
        return
    try:
        atomic_write(last_good_path(path), raw.decode("utf-8-sig"), fsync=True)
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("保存 %s 的上一份完好副本失败: %s", path, exc)


def read_with_fallback[T](
    path: Path, parse: Callable[[str], T]
) -> tuple[T | None, str | None, bool]:
    """读 *path*，返回 ``(内容, 说明, 文件本身是否完好)``。

    - 文件不存在：``(None, None, True)``。
    - 完好：``(内容, None, True)``。
    - 读不懂但 ``.lastgood`` 完好：``(副本内容, 说明, False)``。
    - 都读不懂：``(None, 说明, False)``。
    """
    raw = _read_bytes(path)
    if raw is None:
        return None, None, True
    try:
        return _parse(raw, parse), None, True
    except Exception as exc:
        reason = f"{path} 读不懂（{exc}）"
    backup = last_good_path(path)
    backup_raw = _read_bytes(backup)
    if backup_raw is not None:
        try:
            data = _parse(backup_raw, parse)
        except Exception:
            pass
        else:
            note = f"{reason}，改用上一份完好的副本 {backup}"
            logger.warning(note)
            return data, note, False
    return None, reason, False


def remove_last_good(path: Path) -> None:
    try:
        os.unlink(last_good_path(path))
    except FileNotFoundError:
        pass
