from pathlib import Path

from core.hook_scanner import HookScanner
from core.services.config_service import ConfigService


class HookService:
    """管理和扫描钩子资源的业务服务。"""

    def __init__(self, hooks_root: Path, config_path: Path):
        """使用钩子根目录与配置文件路径初始化 ``HookService``。

        Args:
            hooks_root: 钩子根目录。
            config_path: 配置文件路径。
        """
        self.hooks_root = hooks_root
        self.config_path = config_path
        self.scanner = HookScanner(hooks_root)

    def get_detailed_hooks(self, group: str | None = None) -> list[dict]:
        """扫描全部钩子并结合配置计算激活状态。

        Args:
            group: 指定资源组时仅检查该组（兼容 ``groups.<group>.hooks`` 与旧版
                ``hooks.project_hooks.<group>``）；为 ``None`` 时汇总所有组。

        Returns:
            包含 ``id`` / ``name`` / ``event`` / ``description`` / ``path`` / ``isActive``
            字段的字典列表。
        """
        scanned, _ = self.scanner.scan()

        # 通过 ConfigService 读取，确保复用校验/损坏副本保护与缓存逻辑
        config, _ = ConfigService(self.config_path).get_config()
        active_hooks: set[str] = set()

        def _collect_hook_list(items: object) -> None:
            if isinstance(items, list):
                active_hooks.update(item for item in items if isinstance(item, str))

        groups_cfg = config.get("groups")
        legacy_cfg = (
            config.get("hooks", {}).get("project_hooks")
            if isinstance(config.get("hooks"), dict)
            else None
        )

        if group is not None:
            if isinstance(groups_cfg, dict) and isinstance(groups_cfg.get(group), dict):
                _collect_hook_list(groups_cfg[group].get("hooks"))
            if isinstance(legacy_cfg, dict):
                _collect_hook_list(legacy_cfg.get(group))
        else:
            if isinstance(groups_cfg, dict):
                for group_def in groups_cfg.values():
                    if isinstance(group_def, dict):
                        _collect_hook_list(group_def.get("hooks"))
            if isinstance(legacy_cfg, dict):
                for hooks in legacy_cfg.values():
                    _collect_hook_list(hooks)

        hooks_list = []
        for category, hooks in scanned.items():
            for hook_name, metadata in hooks.items():
                hook_id = f"{category}/{hook_name}"
                hooks_list.append(
                    {
                        "id": hook_id,
                        "name": metadata.get("name", hook_name),
                        "event": metadata.get("event", "Unknown"),
                        "description": metadata.get("description", ""),
                        "path": metadata.get("_hook_dir", ""),
                        "isActive": hook_id in active_hooks,
                    }
                )
        return hooks_list
