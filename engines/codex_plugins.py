"""Plugin marketplace and installation management for the Codex engine."""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.injection_ledger import InjectionLedger
from core.logging_config import get_logger

logger = get_logger(__name__)


class CodexPluginMixin:
    """Plugin and marketplace lifecycle mixin for CodexEngine."""

    # Provided by BaseEngine and its mixins (_LinksMixin, _SettingsMixin, _ConfigMixin).
    if TYPE_CHECKING:

        def _is_windows_link(self, path: Path) -> bool: ...
        def _safe_remove_link(self, path: Path) -> None: ...
        def _create_skill_link(self, source: Path, target: Path) -> None: ...
        def get_plugins_to_mount(self) -> list[dict[str, Any]]: ...
        def _load_config(self, path: Path) -> Any: ...
        def _save_config(self, path: Path, data: Any) -> None: ...

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

    def _withdraw_codeagent_plugins(
        self, config_path: Path, created: list[Any]
    ) -> bool:
        """只摘掉本工具名下的市场和插件项，别的内容原样保留。

        这些键都带着 ``MARKETPLACE_NAME`` 命名空间，归属一目了然，没有账本
        （旧版本的残留）也能安全收回。返回是否处理完毕。
        """
        if not config_path.exists():
            return True
        data = self._load_config(config_path)
        if not isinstance(data, dict):
            logger.warning(
                "无法解析 %s，本工具登记的插件没有收回；修好文件后再启动一次 ca codex",
                config_path,
            )
            return False

        modified = False
        marketplaces = data.get("marketplaces")
        if isinstance(marketplaces, dict) and self.MARKETPLACE_NAME in marketplaces:
            del marketplaces[self.MARKETPLACE_NAME]
            modified = True
        plugins = data.get("plugins")
        if isinstance(plugins, dict):
            for ext_id in [
                k for k in plugins.keys() if k.endswith(f"@{self.MARKETPLACE_NAME}")
            ]:
                del plugins[ext_id]
                modified = True
        for marker in created:
            if (
                isinstance(marker, list)
                and len(marker) == 1
                and marker[0] in data
                and isinstance(data[marker[0]], dict)
                and not data[marker[0]]
            ):
                del data[marker[0]]
                modified = True

        if modified:
            self._save_config(config_path, data)
            logger.info("Removed CodeAgent plugins from %s", config_path)
        return True

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
        """把本工具的插件市场和插件登记进用户级 ``~/.codex/config.toml``。

        写了什么记在注入账本里（:mod:`core.injection_ledger`），退出时只收回
        这些。不再整文件备份：codex 会话期间自己也会写这个文件（项目信任、
        ``/model`` 的选择），整文件还原会把这些改动一起抹掉。
        """
        plugins = self.get_plugins_to_mount()
        if not plugins:
            return

        config_path = self._get_user_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

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

        ledger = InjectionLedger(config_path)
        ledger.begin()
        for table in ("marketplaces", "plugins"):
            if table not in data:
                ledger.note_created([table])
        data = self._format_plugins_for_settings(data, plugins)
        ledger.save()
        self._save_config(config_path, data)
        ledger.commit()
        logger.info("Registered Codex plugins in %s", config_path)

    def cleanup_plugins_available(self) -> None:
        """收回全局配置里本工具的登记，并清理临时市场/缓存。"""
        config_path = self._get_user_config_path()
        ledger = InjectionLedger(config_path)
        has_ledger = ledger.load()

        if has_ledger and ledger.untouched_since_commit():
            ledger.restore_original()
            ledger.delete()
            logger.info("Restored %s to its pre-injection content", config_path.name)
        elif self._withdraw_codeagent_plugins(config_path, ledger.created):
            ledger.delete()

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
