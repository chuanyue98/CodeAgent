"""把当前项目组的技能包装成引擎原生的插件市场（marketplace）。

CodeBuddy 不认 Claude 风格的 ``skills/`` 目录，它的技能要经插件市场分发：
市场根目录放 ``.codebuddy-plugin/marketplace.json`` 声明插件清单，每个插件用
``skills`` 字段指向自己的目录，而插件目录里就是一份 ``SKILL.md`` —— 与
CodeAgent 的技能格式完全一致（实测 codebuddy 官方市场里的 ``algorithmic-art``
等插件就是这个结构），所以技能可以原样链接过去，不需要转换。

市场本身注册进用户级的 ``known_marketplaces.json``，但**启用哪些插件是每次启动
用 ``--channels`` 现给的**，由当前项目组决定。注册会在最后一个会话退出时还原。

技能是**复制**进市场而不是链接：CodeBuddy 安装插件时会检查源路径 resolve 之后
是否仍在市场根内，链接到仓库里的 ``skills/`` 会被判为
``Plugin source path escapes marketplace root`` 而拒绝。技能都是小体积的
Markdown，每次启动重建一份的代价可以忽略，改了源文件下次启动即生效。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.logging_config import get_logger
from core.utils.atomic_write import atomic_write

if TYPE_CHECKING:
    from core.link_manager import LinkManager

logger = get_logger(__name__)

#: 注册进引擎的市场名，也是 ``--channels plugin:<name>@<此名>`` 的后半段。
MARKETPLACE_NAME = "codeagent-local"


class _MarketplaceMixin:
    """需要经插件市场分发技能的引擎（目前是 CodeBuddy）。"""

    if TYPE_CHECKING:
        link_manager: LinkManager

        def resolve_skill_sources(self) -> list[tuple[str, Path]]: ...

    def _get_marketplace_root(self) -> Path:
        """市场落地目录。

        放在 ``.tmp/`` 而不是引擎自己的 ``plugins/marketplaces/``：那里是引擎
        管理的地盘，写进去会和它的自动更新、内置市场清单搅在一起。
        """
        raise NotImplementedError

    def _get_known_marketplaces_path(self) -> Path:
        """引擎记录已知市场的 JSON 文件。"""
        raise NotImplementedError

    def ensure_marketplace(self) -> list[str]:
        """按当前项目组生成市场并注册，返回可用插件名。

        没有技能可挂时返回空列表，并把上一次留下的注册撤掉——项目组换成一个
        不带技能的组时，旧市场不该继续挂在那里。
        """
        skills = self.resolve_skill_sources()
        if not skills:
            self.cleanup_marketplace()
            return []

        root = self._get_marketplace_root()
        plugins_dir = root / "plugins"
        # 整个 plugins/ 目录由本方法独占，清空重建最省事，也顺带摘掉上一次挂了
        # 而这次不在组里的技能。
        if plugins_dir.exists():
            shutil.rmtree(plugins_dir)
        plugins_dir.mkdir(parents=True)

        entries: list[dict[str, Any]] = []
        names: list[str] = []
        for target_name, skill_src in skills:
            try:
                shutil.copytree(skill_src, plugins_dir / target_name)
            except Exception as exc:
                logger.warning("Failed to copy skill '%s': %s", target_name, exc)
                continue
            names.append(target_name)
            entries.append(
                {
                    "name": target_name,
                    "description": _describe(skill_src),
                    "source": f"./plugins/{target_name}",
                    "version": "1.0.0",
                    "skills": [f"./plugins/{target_name}"],
                }
            )

        if not entries:
            self.cleanup_marketplace()
            return []

        manifest_dir = root / ".codebuddy-plugin"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(
            manifest_dir / "marketplace.json",
            json.dumps(
                {
                    "name": MARKETPLACE_NAME,
                    "description": "CodeAgent 当前项目组的技能",
                    "plugins": entries,
                },
                indent=2,
                ensure_ascii=False,
            ),
        )

        self._register_marketplace(root)
        logger.info("Marketplace ready: %d skills as plugins", len(names))
        return names

    def cleanup_marketplace(self) -> None:
        """撤掉注册。市场目录留着，下次启动会按新的项目组重写。"""
        path = self._get_known_marketplaces_path()
        known = _load_json(path)
        if not isinstance(known, dict) or MARKETPLACE_NAME not in known:
            return
        del known[MARKETPLACE_NAME]
        if known:
            atomic_write(path, json.dumps(known, indent=2, ensure_ascii=False))
        else:
            # 文件本来就是我们建的（引擎自带市场一个不剩），别留个空壳。
            path.unlink(missing_ok=True)
        logger.info("Marketplace unregistered")

    def _register_marketplace(self, root: Path) -> None:
        path = self._get_known_marketplaces_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        known = _load_json(path)
        if not isinstance(known, dict):
            known = {}
        known[MARKETPLACE_NAME] = {
            "manifestName": MARKETPLACE_NAME,
            "type": "directory",
            "source": {"source": "directory", "path": str(root)},
            "installLocation": str(root),
            "description": "CodeAgent local skills",
            "autoUpdate": False,
            "isBuiltIn": False,
        }
        atomic_write(path, json.dumps(known, indent=2, ensure_ascii=False))

    def channel_args(self, plugin_names: list[str]) -> list[str]:
        """``--channels`` 参数，没有插件时返回空列表（不能传空串）。"""
        if not plugin_names:
            return []
        channels = ",".join(f"plugin:{n}@{MARKETPLACE_NAME}" for n in plugin_names)
        return ["--channels", channels]


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _describe(skill_src: Path) -> str:
    """取技能 frontmatter 里的 description，失败就用名字兜底。"""
    skill_md = skill_src / "SKILL.md"
    try:
        for line in skill_md.read_text(encoding="utf-8").splitlines()[:10]:
            if line.startswith("description:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return skill_src.name
