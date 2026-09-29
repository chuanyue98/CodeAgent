"""Plugin marketplace and installation management for the Codex engine."""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logging_config import get_logger

logger = get_logger(__name__)


class CodexPluginMixin:
    """Plugin and marketplace lifecycle mixin for CodexEngine."""

    MARKETPLACE_NAME: str

    def _get_codex_home(self) -> Path:
        return (Path.home() / ".codex").resolve()

    def _get_user_config_path(self) -> Path:
        return self._get_codex_home() / "config.toml"

    def _get_marketplace_root(self) -> Path:
        return (
            self._get_codex_home() / ".tmp" / "marketplaces" / self.MARKETPLACE_NAME
        ).resolve()

    def _get_plugin_cache_root(self) -> Path:
        return (
            self._get_codex_home() / "plugins" / "cache" / self.MARKETPLACE_NAME
        ).resolve()

    def _format_codex_local_path(self, path: Path) -> str:
        resolved = path.resolve()
        if os.name == "nt":
            raw = str(resolved)
            if not raw.startswith("\\\\?\\"):
                return f"\\\\?\\{raw}"
            return raw
        return resolved.as_posix()

    def _prepare_local_marketplace(self, plugins: list[dict]) -> Path:
        marketplace_root = self._get_marketplace_root()
        plugins_root = marketplace_root / "plugins"
        marketplace_plugins_dir = marketplace_root / ".agents" / "plugins"
        plugins_root.mkdir(parents=True, exist_ok=True)
        marketplace_plugins_dir.mkdir(parents=True, exist_ok=True)

        marketplace_entries: list[dict[str, Any]] = []
        for plugin_meta in plugins:
            plugin_name = plugin_meta["name"]
            plugin_src = plugin_meta.get("_plugin_dir")
            if not plugin_src:
                continue

            plugin_src_path = Path(plugin_src).resolve()
            target_link = plugins_root / plugin_name

            if target_link.exists():
                try:
                    if self._is_windows_link(target_link) or target_link.is_symlink():
                        if target_link.resolve() != plugin_src_path:
                            self._safe_remove_link(target_link)
                    else:
                        continue
                except Exception:
                    self._safe_remove_link(target_link)

            if not target_link.exists():
                self._create_skill_link(plugin_src_path, target_link)

            category = (
                plugin_meta.get("interface", {}).get("category")
                or plugin_meta.get("category")
                or "Custom"
            )
            marketplace_entries.append(
                {
                    "name": plugin_name,
                    "source": {
                        "source": "local",
                        "path": f"./plugins/{plugin_name}",
                    },
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": category,
                }
            )

        marketplace_payload = {
            "name": self.MARKETPLACE_NAME,
            "interface": {"displayName": "CodeAgent Local"},
            "plugins": marketplace_entries,
        }
        marketplace_path = marketplace_plugins_dir / "marketplace.json"
        marketplace_path.write_text(
            json.dumps(marketplace_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return marketplace_root

    def _ensure_cached_plugin_install(
        self, plugin_name: str, plugin_src_path: Path
    ) -> None:
        cache_root = self._get_plugin_cache_root() / plugin_name
        cache_root.mkdir(parents=True, exist_ok=True)
        installed_path = cache_root / "local"

        if installed_path.exists():
            try:
                if self._is_windows_link(installed_path) or installed_path.is_symlink():
                    if installed_path.resolve() == plugin_src_path.resolve():
                        return
                    self._safe_remove_link(installed_path)
                elif installed_path.is_dir():
                    shutil.rmtree(installed_path)
                else:
                    installed_path.unlink()
            except Exception:
                if installed_path.is_dir():
                    shutil.rmtree(installed_path, ignore_errors=True)
                else:
                    installed_path.unlink(missing_ok=True)

        self._create_skill_link(plugin_src_path, installed_path)

    def _format_plugins_for_settings(self, data: Any, plugins: list[dict]) -> Any:
        """实现 Codex 特有的插件注册逻辑 (marketplace + cache install + enabled 状态)"""
        import tomlkit

        marketplace_root = self._prepare_local_marketplace(plugins)

        if "marketplaces" not in data:
            data["marketplaces"] = tomlkit.table()
        if "plugins" not in data:
            data["plugins"] = tomlkit.table()

        if self.MARKETPLACE_NAME not in data["marketplaces"]:
            data["marketplaces"][self.MARKETPLACE_NAME] = tomlkit.table()
        data["marketplaces"][self.MARKETPLACE_NAME]["last_updated"] = datetime.now(
            UTC
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        data["marketplaces"][self.MARKETPLACE_NAME]["source_type"] = "local"
        data["marketplaces"][self.MARKETPLACE_NAME]["source"] = (
            self._format_codex_local_path(marketplace_root)
        )

        allowed_plugin_ids = {
            f"{plugin_meta['name']}@{self.MARKETPLACE_NAME}" for plugin_meta in plugins
        }
        for ext_id in list(data["plugins"].keys()):
            if (
                ext_id.endswith(f"@{self.MARKETPLACE_NAME}")
                and ext_id not in allowed_plugin_ids
            ):
                if isinstance(data["plugins"][ext_id], dict):
                    data["plugins"][ext_id]["enabled"] = False

        for plugin_meta in plugins:
            plugin_name = plugin_meta["name"]
            plugin_src = plugin_meta.get("_plugin_dir")
            if not plugin_src:
                continue

            self._ensure_cached_plugin_install(plugin_name, Path(plugin_src).resolve())
            ext_id = f"{plugin_name}@{self.MARKETPLACE_NAME}"

            if ext_id not in data["plugins"]:
                data["plugins"][ext_id] = tomlkit.table()

            data["plugins"][ext_id]["enabled"] = True

        return data

    def ensure_plugins_available(self) -> None:
        plugins = self.get_plugins_to_mount()
        if not plugins:
            return

        config_path = self._get_user_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # 备份全局配置。不再依赖 ``not backup_path.exists()`` 仅首次创建：
        # 每次都刷新备份（覆盖旧的），确保即使上一轮崩溃导致备份缺失也能
        # 重新建立。但若 config 已带有本工具的注入痕迹（说明上次崩溃未还
        # 原），则保留现有干净备份，避免把脏 config 覆盖掉干净备份导致后续
        # 永久无法还原。
        backup_path = config_path.with_suffix(".toml.bak")
        if config_path.exists():
            try:
                current_content = config_path.read_text(encoding="utf-8")
            except Exception:
                current_content = ""
            if self.MARKETPLACE_NAME not in current_content:
                shutil.copy2(config_path, backup_path)
                logger.info(
                    "Created safety backup of global config: %s", backup_path.name
                )

        data = self._load_config(config_path)
        if data is None:
            logger.warning(
                "Skipping plugin injection into %s: file exists but could not be read or parsed",
                config_path,
            )
            return
        if not isinstance(data, dict):
            logger.warning(
                "Skipping plugin injection into %s: expected dict/table root, got %s",
                config_path,
                type(data).__name__,
            )
            return
        data = self._format_plugins_for_settings(data, plugins)
        self._save_config(config_path, data)
        logger.info("Registered Codex plugins in %s", config_path)

    def cleanup_plugins_available(self) -> None:
        """还原全局配置并清理临时市场/缓存"""
        config_path = self._get_user_config_path()
        backup_path = config_path.with_suffix(".toml.bak")

        if backup_path.exists():
            # 使用 copy 而非 move(os.replace) 还原，保留备份副本，确保下一轮
            # 仍可从干净备份还原（即使本轮再次崩溃）。
            shutil.copy2(backup_path, config_path)
            logger.info("Restored global config from backup: %s", backup_path.name)
        else:
            # 兜底：若没有备份（罕见），则清理配置中本工具的 marketplaces 与 plugins 项
            data = self._load_config(config_path)
            if data and isinstance(data, dict):
                modified = False
                if (
                    "marketplaces" in data
                    and self.MARKETPLACE_NAME in data["marketplaces"]
                ):
                    del data["marketplaces"][self.MARKETPLACE_NAME]
                    modified = True
                if "plugins" in data and isinstance(data["plugins"], dict):
                    to_remove = [
                        k
                        for k in data["plugins"].keys()
                        if k.endswith(f"@{self.MARKETPLACE_NAME}")
                    ]
                    for k in to_remove:
                        del data["plugins"][k]
                        modified = True
                if modified:
                    self._save_config(config_path, data)
                    logger.info("Removed CodeAgent plugins from %s", config_path)

        marketplace_root = self._get_marketplace_root()
        if marketplace_root.exists():
            plugins_link = marketplace_root / "plugins"
            if plugins_link.exists() and (
                self._is_windows_link(plugins_link) or plugins_link.is_symlink()
            ):
                self._safe_remove_link(plugins_link)
            shutil.rmtree(marketplace_root, ignore_errors=True)
            logger.info("Cleaned up local Codex marketplace")

        cache_root = self._get_plugin_cache_root()
        if cache_root.exists():
            shutil.rmtree(cache_root, ignore_errors=True)
            logger.info("Cleaned up local Codex plugin cache")
