"""把当前项目组的技能和插件挂进 CodeBuddy。

CodeBuddy 不认 Claude 风格的 ``skills/`` 目录，技能得装在插件里。但插件不必
进市场、也不必安装：``CODEBUDDY_PLUGIN_DIRS`` 里的每个目录都会被当成一个
**inline 插件**直接加载，状态默认就是 enabled，只有用户级 settings 的
``enabledPlugins["<name>@inline"]`` 显式为 false 才会被关掉。

所以这里把整组技能包成**一个**名叫 ``codeagent`` 的插件，形状是
``<root>/.codebuddy-plugin/plugin.json`` + ``<root>/skills/<名>/SKILL.md``。
manifest 不声明 ``skills``：引擎发现插件没写这个字段时会自己扫 ``skills/``。

项目组自己声明的插件跟在后面一起挂。它们是 Claude 风格的插件，但
CodeBuddy 认的清单目录里就有 ``.claude-plugin``，可以原样加载。

用环境变量而不是等价的 ``--plugin-dir``：后者必须插在子命令之前，和原生参数
透传的拼法打架。

技能是**复制**进去的而不是链接：复制这条路实测端到端跑通（技能出现在模型的
技能列表里），链接只验到「插件能被加载」那一层。技能都是小体积 Markdown，
每次启动重建一份的代价可以忽略，改了源文件下次启动即生效。

插件目录按项目分开：同一台机器上不同项目的会话可能挂着不同的技能组，共用一个
目录会互相覆盖。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.logging_config import get_logger
from core.utils.atomic_write import atomic_write

logger = get_logger(__name__)

#: 插件名，也是模型看到的 ``<此名>@inline``。
PLUGIN_NAME = "codeagent"

#: 引擎据此加载 inline 插件，多个目录用 ``os.pathsep`` 分隔。
PLUGIN_DIRS_ENV = "CODEBUDDY_PLUGIN_DIRS"

#: 引擎认的插件清单目录，另外两个是 ``.workbuddy-plugin`` / ``.claude-plugin``。
_MANIFEST_DIR = ".codebuddy-plugin"


class _PluginDirMixin:
    """需要把技能包成 inline 插件的引擎（目前是 CodeBuddy）。"""

    if TYPE_CHECKING:

        def resolve_skill_sources(self) -> list[tuple[str, Path]]: ...
        def get_plugins_to_mount(self) -> list[dict[str, Any]]: ...

    def _get_plugin_dir_root(self) -> Path:
        """插件落地目录的父目录。"""
        raise NotImplementedError

    def _get_project_dir(self, project: Path) -> Path:
        digest = hashlib.sha256(str(project.resolve()).encode("utf-8")).hexdigest()
        return self._get_plugin_dir_root() / digest[:16]

    def _get_plugin_dir(self, project: Path) -> Path:
        return self._get_project_dir(project) / PLUGIN_NAME

    def ensure_plugin_dir(self, project: Path) -> Path | None:
        """生成插件目录，返回它的路径；没有技能可挂时返回 ``None``。"""
        skills = self.resolve_skill_sources()
        if not skills:
            self.cleanup_plugin_dir(project)
            return None

        root = self._get_plugin_dir(project)
        skills_dir = root / "skills"
        # 整个 skills/ 由本方法独占，清空重建最省事，也顺带摘掉上一次挂了而
        # 这次不在组里的技能。
        if skills_dir.exists():
            shutil.rmtree(skills_dir)
        skills_dir.mkdir(parents=True)

        copied = 0
        for target_name, skill_src in skills:
            try:
                shutil.copytree(skill_src, skills_dir / target_name)
            except Exception as exc:
                logger.warning("Failed to copy skill '%s': %s", target_name, exc)
                continue
            copied += 1

        if not copied:
            self.cleanup_plugin_dir(project)
            return None

        manifest_dir = root / _MANIFEST_DIR
        manifest_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(
            manifest_dir / "plugin.json",
            json.dumps(
                {
                    "name": PLUGIN_NAME,
                    "description": "CodeAgent 当前项目组的技能",
                    "version": "1.0.0",
                },
                indent=2,
                ensure_ascii=False,
            ),
        )

        logger.info("Plugin dir ready: %d skills", copied)
        return root

    def cleanup_plugin_dir(self, project: Path) -> None:
        """删掉本项目的插件目录。没挂过也不报错。"""
        project_dir = self._get_project_dir(project)
        if not project_dir.exists():
            return
        shutil.rmtree(project_dir, ignore_errors=True)
        logger.info("Plugin dir removed")

    def resolve_group_plugin_dirs(self) -> list[Path]:
        """项目组自己声明的插件目录，解析不出目录的条目跳过。"""
        dirs: list[Path] = []
        for plugin_meta in self.get_plugins_to_mount():
            source = plugin_meta.get("_plugin_dir")
            if not source:
                continue
            path = Path(source)
            if path.is_dir():
                dirs.append(path)
            else:
                logger.warning(
                    "Skip plugin '%s': %s is not a directory",
                    plugin_meta.get("name"),
                    path,
                )
        return dirs

    def plugin_dir_env(self, plugin_dir: Path | None) -> dict[str, str]:
        """要并进引擎环境的变量；没有任何插件可挂时为空。"""
        dirs = ([plugin_dir] if plugin_dir is not None else []) + (
            self.resolve_group_plugin_dirs()
        )
        if not dirs:
            return {}
        return {PLUGIN_DIRS_ENV: os.pathsep.join(str(d) for d in dirs)}
