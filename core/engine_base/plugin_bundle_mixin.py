"""把当前项目组的技能打包成引擎原生的插件（bundle）。

Antigravity 既不认 Claude 风格的 ``skills/`` 目录，也没有插件市场：它的扩展
单位是 ``<config>/plugins/<name>/`` 下的一个插件，插件自带 ``plugin.json``
（只需要一个 ``name``）以及 ``skills/``、``hooks/`` 子目录，再由
``<config>/config.json`` 的 ``plugins.<name>.enabled`` 决定启不启用——实测
``~/.gemini/config/plugins/superpowers`` 就是这个形状。

所以这里把整组技能包成**一个**名叫 ``codeagent`` 的插件，技能以链接挂进它的
``skills/``。启用标志在最后一个会话退出时撤掉，插件目录留着按下次的项目组重写。

codeagent MCP（跨引擎委派）也走这个插件：Antigravity 没有单会话挂 MCP 的参数，
但会读插件目录下的 ``mcp_config.json``（实测；写在 ``plugin.json`` 里不生效）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.delegation_depth import MCP_SERVER_NAME, codeagent_mcp_server
from core.logging_config import get_logger
from core.utils.atomic_write import atomic_write

logger = get_logger(__name__)

#: 插件名，同时是 ``plugins/<此名>/`` 和 ``config.json`` 里的键。
BUNDLE_NAME = "codeagent"


class _PluginBundleMixin:
    """需要把技能包成单个原生插件的引擎（目前是 Antigravity）。"""

    if TYPE_CHECKING:

        def resolve_skill_sources(self) -> list[tuple[str, Path]]: ...
        def _ensure_managed_link(
            self, source: Path, target: Path, link_path: Path
        ) -> bool: ...
        def _remove_stale_managed_links(
            self, link_path: Path, desired_names: set[str]
        ) -> None: ...

    def _get_plugin_config_dir(self) -> Path:
        """引擎的 customization root，``plugins/`` 和 ``config.json`` 都在这儿。"""
        raise NotImplementedError

    def ensure_plugin_bundle(self) -> bool:
        """生成插件并在 config 里启用，返回是否真的挂上了东西（技能或 MCP）。"""
        skills = self.resolve_skill_sources()
        server = codeagent_mcp_server()
        bundle = self._get_plugin_config_dir() / "plugins" / BUNDLE_NAME
        # 被委派出来的会话不挂：删掉上一个会话留下的声明。
        mcp_config = bundle / "mcp_config.json"
        if not skills and server is None:
            mcp_config.unlink(missing_ok=True)
            self.cleanup_plugin_bundle()
            return False

        skills_dir = bundle / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        if server is None:
            mcp_config.unlink(missing_ok=True)
        else:
            atomic_write(
                mcp_config,
                json.dumps(
                    {"mcpServers": {MCP_SERVER_NAME: server}},
                    indent=2,
                    ensure_ascii=False,
                ),
            )

        # 上一次挂的、这次不在组里的技能先摘掉，否则换组后旧技能还留着。
        self._remove_stale_managed_links(skills_dir, {name for name, _ in skills})

        linked = 0
        for target_name, skill_src in skills:
            try:
                # 用托管链接而不是裸 symlink：目标已存在时要按 manifest 判断是
                # 我们上次挂的（复用）还是用户自己的东西（不动），裸 symlink
                # 在第二次启动就会 FileExistsError。
                self._ensure_managed_link(
                    skill_src, skills_dir / target_name, skills_dir
                )
            except Exception as exc:
                logger.warning("Failed to link skill '%s': %s", target_name, exc)
                continue
            linked += 1

        if not linked and server is None:
            self.cleanup_plugin_bundle()
            return False

        atomic_write(
            bundle / "plugin.json",
            json.dumps({"name": BUNDLE_NAME}, indent=2, ensure_ascii=False),
        )
        self._set_enabled(True)
        logger.info(
            "Plugin bundle ready: %d skills, mcp=%s", linked, server is not None
        )
        return True

    def cleanup_plugin_bundle(self) -> None:
        """撤掉启用标志。插件目录留着，下次启动按新的项目组重写。"""
        self._set_enabled(False)

    def _set_enabled(self, enabled: bool) -> None:
        path = self._get_plugin_config_dir() / "config.json"
        config = _load_json(path)
        if not isinstance(config, dict):
            config = {}
        plugins = config.get("plugins")
        if not isinstance(plugins, dict):
            plugins = {}

        if enabled:
            plugins[BUNDLE_NAME] = {"enabled": True}
        elif BUNDLE_NAME in plugins:
            del plugins[BUNDLE_NAME]
        else:
            return  # 没注册过，别白写一次盘

        # 用户自己装的插件（如 superpowers）在同一个字典里，只动我们这一条。
        config["plugins"] = plugins
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, json.dumps(config, indent=2, ensure_ascii=False))


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
