from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.injection_ledger import InjectionLedger
from core.logging_config import get_logger
from core.utils.atomic_write import atomic_write

logger = get_logger(__name__)


class SettingsFile:
    """Reads and writes a settings file.

    Defaults to JSON, but switches to TOML for ``.toml`` paths — codex keeps
    its hook configuration in ``config.toml`` rather than a JSON settings
    file, and writing JSON there produced a file codex never read.
    """

    def __init__(self, path: Path):
        self.path = path
        self.is_toml = path.suffix.lower() == ".toml"

    def load(self) -> Any:
        if not self.path.exists():
            return {}
        try:
            text = self.path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to read settings file %s: %s", self.path, exc)
            return None
        try:
            if self.is_toml:
                import tomlkit

                return tomlkit.parse(text)
            return json.loads(text)
        except Exception as exc:
            logger.warning("Failed to parse settings file %s: %s", self.path, exc)
            return None

    def save(self, data: Any):
        if self.is_toml:
            import tomlkit

            atomic_write(self.path, tomlkit.dumps(data))
            return
        atomic_write(self.path, json.dumps(data, indent=2, ensure_ascii=False))

    def is_injected(self) -> bool:
        """True if this file carries the old whole-file injection marker."""
        data = self.load()
        return isinstance(data, dict) and data.get("_ca_injected") is True

    def restore_backup(self) -> bool:
        """旧版本留下的 ``.bak`` 整文件备份：存在就拷回。只用于兼容旧残留。"""
        backup_path = self.path.with_name(self.path.name + ".bak")
        if backup_path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(backup_path), str(self.path))
            return True
        return False


def plain(value: Any) -> Any:
    """把 tomlkit 的条目换成普通的 dict/list，便于比较和写进账本。"""
    unwrap = getattr(value, "unwrap", None)
    if callable(unwrap):
        value = unwrap()
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def _hook_marker(*parts: str) -> list[str]:
    return ["hooks", *parts]


def _star_group(groups: Any) -> Any:
    if not isinstance(groups, list):
        return None
    return next(
        (g for g in groups if isinstance(g, dict) and g.get("matcher") == "*"),
        None,
    )


def _index_by_name(items: list[Any], name: Any) -> int | None:
    return next(
        (
            i
            for i, item in enumerate(items)
            if isinstance(item, dict) and item.get("name") == name
        ),
        None,
    )


class SettingsManager:
    """往引擎的 settings 文件里注入钩子，退出时只收回自己写的部分。

    写了什么记在注入账本里（见 :mod:`core.injection_ledger`），不再整个文件
    备份、整个文件还原——那样会把会话期间别人对这个文件的改动一起抹掉。
    """

    def __init__(self, event_map: dict[str, str]):
        self.event_map = event_map

    def inject_hooks(self, settings_path: Path, hooks: list[dict[str, Any]]):
        """Injects hook configurations into a settings file."""
        if not hooks:
            return

        settings_path.parent.mkdir(parents=True, exist_ok=True)

        sf = SettingsFile(settings_path)
        ledger = InjectionLedger(settings_path)
        if not ledger.exists() and sf.is_injected():
            # 旧版本崩溃留下的整文件注入（带 _ca_injected 标记）：先按旧办法
            # 还原成干净文件，再按账本重新注入。
            restore_legacy_injection(settings_path)

        data = sf.load()
        if data is None:
            logger.warning(
                "Skipping hook injection into %s: file exists but could not be read or parsed",
                settings_path,
            )
            return
        if not isinstance(data, dict):
            logger.warning(
                "Skipping hook injection into %s: expected dict/object root, got %s",
                settings_path,
                type(data).__name__,
            )
            return

        ledger.begin()

        if "hooks" not in data:
            data["hooks"] = {}
            ledger.note_created(_hook_marker())

        for hook in hooks:
            event_name = hook.get("event")
            if not event_name:
                continue
            event = self.event_map.get(event_name, event_name)
            if event not in data["hooks"]:
                data["hooks"][event] = [{"matcher": "*", "hooks": []}]
                ledger.note_created(_hook_marker(event))
                ledger.note_created(_hook_marker(event, "*"))

            target_group = _star_group(data["hooks"][event])
            if target_group is None:
                data["hooks"][event].append({"matcher": "*", "hooks": []})
                ledger.note_created(_hook_marker(event, "*"))
                # tomlkit 会把追加的 dict 包成自己的表，取回包好的那个再往里写。
                target_group = data["hooks"][event][-1]

            event_hooks = target_group["hooks"]
            index = _index_by_name(event_hooks, hook["name"])
            hook_entry = {
                "name": hook["name"],
                "type": "command",
                "command": hook["command"],
            }

            record = ledger.find_entry(kind="hook", event=event, name=hook["name"])
            if record is None:
                # 第一次写这一条：记下它原先的样子（同名条目可能是用户自己的）。
                record = {
                    "kind": "hook",
                    "event": event,
                    "name": hook["name"],
                    "previous": plain(event_hooks[index])
                    if index is not None
                    else None,
                }
                ledger.entries.append(record)

            if index is not None:
                merged = {**plain(event_hooks[index]), **hook_entry}
                event_hooks[index] = merged
                record["written"] = merged
            else:
                event_hooks.append(hook_entry)
                record["written"] = hook_entry

        # 先记账再写配置文件：中途崩溃时账本记的只会比文件里多，
        # 收回时找不到的条目直接跳过。
        ledger.save()
        sf.save(data)
        ledger.commit()

    def restore_settings(self, settings_path: Path):
        """收回注入：文件没被别人动过就逐字节恢复原文，动过就只摘掉自己写的条目。"""
        ledger = InjectionLedger(settings_path)
        if not ledger.load():
            restore_legacy_injection(settings_path)
            return

        if ledger.untouched_since_commit():
            ledger.restore_original()
            ledger.delete()
            logger.info("Restored %s to its pre-injection content", settings_path.name)
            return

        if withdraw_hooks(settings_path, ledger):
            ledger.delete()


def withdraw_hooks(settings_path: Path, ledger: InjectionLedger) -> bool:
    """只摘掉账本里记的钩子条目，返回是否收回完毕（账本可以删了）。"""
    if not settings_path.exists():
        return True

    sf = SettingsFile(settings_path)
    data = sf.load()
    if not isinstance(data, dict):
        # 文件被改坏了：不碰它，账本留着，ca doctor 会报出来。
        logger.warning(
            "无法解析 %s，注入的钩子没有收回；修好文件后运行 ca doctor --fix",
            settings_path,
        )
        return False

    hooks_root = data.get("hooks")
    if isinstance(hooks_root, dict):
        for record in ledger.entries:
            if record.get("kind") != "hook":
                continue
            group = _star_group(hooks_root.get(record.get("event")))
            if group is None or not isinstance(group.get("hooks"), list):
                continue
            items = group["hooks"]
            index = _index_by_name(items, record.get("name"))
            if index is None:
                continue
            if plain(items[index]) != record.get("written"):
                logger.warning(
                    "%s 里的钩子 %s 在会话期间被改过，保留现状不收回",
                    settings_path.name,
                    record.get("name"),
                )
                continue
            previous = record.get("previous")
            if previous is not None:
                items[index] = previous
            else:
                del items[index]

        # 由深到浅清掉注入时新建、现在已经空了的容器。
        for marker in sorted(
            (m for m in ledger.created if isinstance(m, list)), key=len, reverse=True
        ):
            if len(marker) == 3:
                groups = hooks_root.get(marker[1])
                group = _star_group(groups)
                if (
                    isinstance(groups, list)
                    and group is not None
                    and not group.get("hooks")
                    and set(group.keys()) <= {"matcher", "hooks"}
                ):
                    groups.remove(group)
            elif len(marker) == 2:
                if marker[1] in hooks_root and not hooks_root[marker[1]]:
                    del hooks_root[marker[1]]
            elif len(marker) == 1 and not hooks_root:
                del data["hooks"]

    if ledger.original is None and not data:
        settings_path.unlink(missing_ok=True)
        logger.info("Removed %s (CodeAgent created it)", settings_path.name)
    else:
        sf.save(data)
        logger.info("Withdrew CodeAgent hooks from %s", settings_path.name)
    return True


def restore_legacy_injection(settings_path: Path) -> None:
    """旧版本整文件注入的还原：有 .bak 就拷回，没有且带标记就删掉。"""
    sf = SettingsFile(settings_path)
    if sf.restore_backup():
        logger.info("Restored %s from backup", settings_path.name)
        return

    if settings_path.exists():
        try:
            data = sf.load()
            if isinstance(data, dict) and data.get("_ca_injected") is True:
                settings_path.unlink()
                logger.info("Removed injected %s", settings_path.name)
        except Exception:
            logger.warning(
                "检查 %s 的注入标记失败，文件保持原样", settings_path, exc_info=True
            )
