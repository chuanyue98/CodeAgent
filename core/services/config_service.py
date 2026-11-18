import copy
import json
import os
import threading
import traceback
from pathlib import Path
from typing import Any

from core.utils.atomic_write import atomic_write
from core.utils.last_good import keep_last_good, looks_crash_damaged, read_with_fallback


def _parse_config(text: str) -> dict:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("顶层不是 JSON 对象")
    return data


class ConfigService:
    """管理配置文件与项目注册表的读写服务。"""

    _lock = threading.RLock()
    _cache: dict[Path, tuple[int, int, dict[str, Any], list[str]]] = {}

    def __init__(self, config_path: Path):
        """使用指定配置路径初始化 ``ConfigService``。

        Args:
            config_path: 配置文件路径。
        """
        self.config_path = config_path

    def _read(self) -> tuple[dict, list[str]]:
        """从磁盘读取配置文件（调用方需视情况持有 ``_lock``）。

        读不懂时改用上一份完好的副本（见 :mod:`core.utils.last_good`），
        并在 warnings 里说明，交给调用方提示用户。
        """
        try:
            data, note, _intact = read_with_fallback(self.config_path, _parse_config)
        except Exception as e:
            if os.getenv("CA_DEBUG"):
                traceback.print_exc()
            return {}, [f"Failed to read config.json: {e}"]
        if note is None:
            return data or {}, []
        return data or {}, [f"Failed to parse config.json: {note}"]

    def _read_for_write(self) -> dict:
        """写之前读：文件读不懂就拒绝覆盖，除非它是断电留下的空文件/全 0 文件。

        手改出错的文件里有用户的改动，覆盖掉就丢了；断电损坏的文件里什么都
        没有，接着用上一份完好的副本写下去（损坏的文件会先另存一份）。
        """
        config, warnings = self._read()
        if warnings:
            try:
                damaged = looks_crash_damaged(self.config_path.read_bytes())
            except OSError:
                damaged = False
            if not damaged:
                raise ValueError(
                    f"Refusing to overwrite malformed configuration: {warnings[0]}"
                )
        return config

    def _atomic_write(self, config: dict) -> None:
        """通过临时文件 + fsync + 替换原子写入配置（调用方须持有 ``_lock``）。"""
        keep_last_good(self.config_path, _parse_config)
        atomic_write(
            self.config_path,
            json.dumps(config, indent=2, ensure_ascii=False),
            fsync=True,
        )

    def _cached_read(self) -> tuple[dict, list[str]]:
        """若文件 ``(resolve(), mtime_ns, size)`` 未变，则从类级缓存返回深拷贝。"""
        resolved = self.config_path.resolve()
        with self._lock:
            try:
                st = resolved.stat()
            except FileNotFoundError:
                self._cache.pop(resolved, None)
                return {}, []
            except OSError as exc:
                self._cache.pop(resolved, None)
                return {}, [f"Failed to read config.json: {exc}"]

            cached = self._cache.get(resolved)
            if (
                cached is not None
                and cached[0] == st.st_mtime_ns
                and cached[1] == st.st_size
            ):
                return copy.deepcopy(cached[2]), list(cached[3])

            data, warnings = self._read()
            try:
                after = resolved.stat()
            except OSError:
                self._cache.pop(resolved, None)
            else:
                if after.st_mtime_ns == st.st_mtime_ns and after.st_size == st.st_size:
                    self._cache[resolved] = (
                        st.st_mtime_ns,
                        st.st_size,
                        copy.deepcopy(data),
                        list(warnings),
                    )
                else:
                    self._cache.pop(resolved, None)
            return copy.deepcopy(data), list(warnings)

    def get_config(self) -> tuple[dict, list[str]]:
        """获取当前配置与解析警告列表。"""
        return self._cached_read()

    def update_config(self, config: dict):
        """原子替换整份配置文件，并在锁内失效缓存。"""
        if not isinstance(config, dict):
            raise TypeError("Configuration must be a JSON object")
        resolved = self.config_path.resolve()
        with self._lock:
            self._read_for_write()
            self._atomic_write(config)
            self._cache.pop(resolved, None)

    def modify_config(self, modifier):
        """原子执行读取 -> 修改 -> 写回，并在锁内失效缓存。"""
        resolved = self.config_path.resolve()
        with self._lock:
            config = self._read_for_write()
            config = modifier(config)
            self._atomic_write(config)
            self._cache.pop(resolved, None)

    def add_project(self, path: str, group: str) -> list:
        """原子化添加或更新项目注册表中的条目。"""
        result: list = []

        def _modifier(config: dict) -> dict:
            nonlocal result
            raw_registry = config.get("project_registry")
            registry = list(raw_registry) if isinstance(raw_registry, list) else []
            updated = False
            for item in registry:
                # 注册表是用户可手改的文件：条目缺 path 或不是对象时跳过，
                # 而不是拿 KeyError 把 ca project 崩掉。
                if isinstance(item, dict) and item.get("path") == path:
                    item["group"] = group
                    updated = True
                    break
            if not updated:
                registry.append({"path": path, "group": group})
            config["project_registry"] = registry
            result = copy.deepcopy(registry)
            return config

        self.modify_config(_modifier)
        return result

    def delete_project(self, path: str) -> list:
        """原子化从项目注册表中移除指定路径。"""
        result: list = []

        def _modifier(config: dict) -> dict:
            nonlocal result
            raw_registry = config.get("project_registry")
            registry = raw_registry if isinstance(raw_registry, list) else []
            # 只删除 path 匹配的条目；缺 path / 非对象（用户手改留下的脏数据）
            # 原样保留，避免 item["path"] 抛 KeyError。
            updated_registry = [
                item
                for item in registry
                if not (isinstance(item, dict) and item.get("path") == path)
            ]
            config["project_registry"] = updated_registry
            result = copy.deepcopy(updated_registry)
            return config

        self.modify_config(_modifier)
        return result
