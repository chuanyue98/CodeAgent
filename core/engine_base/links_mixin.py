from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.lock_manager import SessionRegistry
from core.logging_config import get_logger

if TYPE_CHECKING:
    from core.link_manager import LinkManager
    from core.lock_manager import LockManager

logger = get_logger(__name__)


#: ``.agents/skills`` 是跨工具的技能目录约定（Codex 原生读取，Orca、Paseo 等也往这里装）。
AGENTS_SKILLS_DIR = Path(".agents") / "skills"


class _LinksMixin:
    """Shared injection lifecycle and skills/plugins symlink management."""

    #: 引擎自己会读项目级和用户级的 ``.agents/skills``（实测 Codex、OpenCode）。
    #: 为 False 时 ca 把那里的技能一并挂进去。
    READS_AGENTS_SKILLS = False

    # Provided by BaseEngine.__init__ / _ConfigMixin.
    if TYPE_CHECKING:
        lock_manager: "LockManager"
        link_manager: "LinkManager"

        def get_current_project_group(self) -> str: ...
        def get_skills_to_mount(self) -> list[str]: ...
        def get_plugins_to_mount(self) -> list[dict[str, Any]]: ...
        def _get_skill_search_roots(self) -> list[Path]: ...

    @contextmanager
    def shared_injection(
        self,
        scope: Path,
        setup: Callable[[], None],
        teardown: Callable[[], None],
    ) -> Iterator[None]:
        """在 *scope* 上注入资源，同一 *scope* 的并发会话共用这份注入。

        每个会话都会跑一次 *setup*（注入是幂等的），*teardown* 只在最后一个
        会话退出时执行，避免先退出的会话把别人还在用的链接和钩子拆掉。
        *scope* 目录若是注入时才建出来的，拆完后变空就一并删掉。
        """
        registry = SessionRegistry(scope, lock_manager=self.lock_manager)
        try:
            with registry.exclusive():
                registry.join()
                if not scope.exists():
                    registry.note_scope_created()
                setup()
            yield
        finally:
            with registry.exclusive():
                if registry.leave():
                    teardown()
                    if registry.take_scope_created():
                        try:
                            scope.rmdir()
                        except OSError:
                            pass

    def clear_stale_injection(self, scope: Path, cleanup: Callable[[], None]) -> None:
        """在没有存活会话时，清掉 ca 留在工作区 *scope*（如 ``.codex/``）里的注入。

        注入只在最后一个会话正常退出时还原，会话被强杀就会一直留着；早先版本
        写进 ``.claude/``、``.opencode/`` 的东西也靠这里收拾。还有会话在跑时不动，
        免得拆掉它正在用的东西。
        """
        if not scope.exists():
            return
        registry = SessionRegistry(scope, lock_manager=self.lock_manager)
        with registry.exclusive():
            if registry.has_live_sessions():
                return
            cleanup()
            if registry.take_scope_created():
                try:
                    scope.rmdir()
                except OSError:
                    pass

    def resolve_skill_sources(self) -> list[tuple[str, Path]]:
        """要挂载的技能，按 (链接名, 源目录) 返回；重名时保留优先级高的来源。

        先是当前项目组的技能，再是引擎自己不读的 ``.agents/skills`` 里的技能。
        """
        resolved = self._resolve_group_skill_sources()
        if self.READS_AGENTS_SKILLS:
            return resolved
        names = {name for name, _ in resolved}
        extra = [
            (name, src)
            for name, src in self._agents_skill_sources(Path.cwd())
            if name not in names
        ]
        if extra:
            logger.info("Mounting %d skill(s) from .agents/skills", len(extra))
        return resolved + extra

    def _native_skill_dirs(self, project: Path) -> list[Path]:
        """引擎自己就会去读的技能目录；那里已有的同名技能不必再从 ``.agents`` 挂。"""
        return []

    def _agents_skill_sources(self, project: Path) -> list[tuple[str, Path]]:
        """项目（从 cwd 往上到 git 根）和用户家目录下 ``.agents/skills`` 里的技能。

        近处的优先；引擎自己目录里已有同名技能的跳过——不少安装器会把同一份
        技能同时拷进 ``~/.agents/skills`` 和 ``~/.claude/skills``。
        """
        roots: list[Path] = []
        current = project.resolve()
        for directory in (current, *current.parents):
            roots.append(directory / AGENTS_SKILLS_DIR)
            if (directory / ".git").exists():
                break
        roots.append(Path.home() / AGENTS_SKILLS_DIR)

        native = self._native_skill_dirs(project)
        found: dict[str, Path] = {}
        seen_roots: set[Path] = set()
        for root in roots:
            if root in seen_roots or not root.is_dir():
                continue
            seen_roots.add(root)
            for entry in sorted(root.iterdir()):
                name = entry.name
                if name in found or not (entry / "SKILL.md").is_file():
                    continue
                if any((d / name / "SKILL.md").is_file() for d in native):
                    continue
                found[name] = entry.resolve()
        return list(found.items())

    def _resolve_group_skill_sources(self) -> list[tuple[str, Path]]:
        skills_to_mount = self.get_skills_to_mount()
        if not skills_to_mount:
            return []

        skill_roots = self._get_skill_search_roots()

        resolved_skills: list[tuple[str, Path]] = []
        resolved_skill_names = set()

        def append_resolved_skill(target_name: str, skill_src: Path):
            if target_name in resolved_skill_names:
                logger.info(
                    "Skip duplicate skill '%s', keeping higher-priority source and ignoring: %s",
                    target_name,
                    skill_src,
                )
                return
            resolved_skill_names.add(target_name)
            resolved_skills.append((target_name, skill_src))

        for skill_name in skills_to_mount:
            skill_src = None
            for root in skill_roots:
                candidate = (root / skill_name).resolve()
                if candidate.exists():
                    skill_src = candidate
                    break

            if skill_src:
                if skill_src.is_dir() and not (skill_src / "SKILL.md").exists():
                    found_sub_skill = False
                    for sub_item in skill_src.iterdir():
                        if sub_item.is_dir() and (sub_item / "SKILL.md").exists():
                            append_resolved_skill(sub_item.name, sub_item)
                            found_sub_skill = True
                    if not found_sub_skill:
                        logger.warning(
                            "Skill '%s' resolved to %s, but it has no SKILL.md "
                            "(directly or in a subdirectory) -- skipped.",
                            skill_name,
                            skill_src,
                        )
                else:
                    append_resolved_skill(skill_name.split("/")[-1], skill_src)
            else:
                searched = ", ".join(str(root / skill_name) for root in skill_roots)
                logger.warning(
                    "Skill '%s' not found. Searched: %s", skill_name, searched
                )

        if not resolved_skills:
            searched_roots = ", ".join(str(root) for root in skill_roots)
            logger.warning(
                "No mountable skills were resolved. Matched skill groups exist, "
                "but none of the candidate directories contain a valid SKILL.md. "
                "Search roots: %s",
                searched_roots,
            )
            return []

        logger.info(
            "Skills matched group: [%s] (匹配 %d 个根目录，挂载 %d 个技能)",
            self.get_current_project_group(),
            len(skills_to_mount),
            len(resolved_skills),
        )
        return resolved_skills

    def ensure_skills_link(self, target_link_path: str):
        link_path = (Path.cwd() / target_link_path).absolute()

        resolved_skills = self.resolve_skill_sources()
        if not resolved_skills:
            self.link_manager.cleanup_link_dir(link_path)
            return

        link_path.mkdir(parents=True, exist_ok=True)

        desired_names = {target_name for target_name, _ in resolved_skills}
        self.link_manager.remove_stale_managed_links(link_path, desired_names)

        for target_name, skill_src in resolved_skills:
            target_skill_path = link_path / target_name
            try:
                self.link_manager.ensure_managed_link(
                    skill_src, target_skill_path, link_path
                )
            except Exception as e:
                logger.warning("Failed to link skill '%s': %s", target_name, e)

    def _get_plugin_link_dir(self) -> Path | None:
        """Returns the directory where this engine's plugin links should be created.

        Each engine must override this to return its specific plugin directory:
        - Codex:    ~/.codex/plugins/
        - Claude:   <cwd>/.claude/plugins/
        - OpenCode: <cwd>/.opencode/plugins/

        Returns:
            Optional[Path]: The absolute path to the plugin link directory,
                or None if plugins are not supported for this engine.
        """
        return None

    def ensure_plugins_link(self):
        plugins_to_mount = self.get_plugins_to_mount()
        link_dir = self._get_plugin_link_dir()
        if link_dir is None:
            return
        if not plugins_to_mount:
            self.link_manager.cleanup_link_dir(link_dir)
            return
        link_dir.mkdir(parents=True, exist_ok=True)
        desired_names = {
            str(plugin_meta.get("name"))
            for plugin_meta in plugins_to_mount
            if plugin_meta.get("name")
        }
        self.link_manager.remove_stale_managed_links(link_dir, desired_names)

        mounted_count = 0
        for plugin_meta in plugins_to_mount:
            plugin_name = plugin_meta["name"]
            plugin_src_str = plugin_meta.get("_plugin_dir")

            if not plugin_src_str:
                continue

            plugin_src = Path(plugin_src_str).resolve()
            target_link = link_dir / plugin_name

            try:
                if self.link_manager.ensure_managed_link(
                    plugin_src, target_link, link_dir
                ):
                    mounted_count += 1
            except Exception as e:
                logger.warning("Failed to link plugin '%s': %s", plugin_name, e)

        if mounted_count:
            logger.info("Ensured %d plugin links in %s", mounted_count, link_dir)

    def cleanup_plugins_link(self):
        link_dir = self._get_plugin_link_dir()
        if link_dir is None:
            return
        self.link_manager.cleanup_link_dir(link_dir)

    def _create_skill_link(self, source: Path, target: Path):
        self.link_manager.create_skill_link(source, target)

    def _safe_remove_link(self, path: Path):
        self.link_manager.safe_remove_link(path)

    def _load_link_manifest(self, link_path: Path) -> dict[str, str]:
        return self.link_manager.load_manifest(link_path)

    def _save_link_manifest(self, link_path: Path, manifest: dict[str, str]) -> None:
        self.link_manager.save_manifest(link_path, manifest)

    def _managed_link_matches(self, path: Path, source: Path) -> bool:
        return self.link_manager.managed_link_matches(path, source)

    def _ensure_managed_link(self, source: Path, target: Path, link_path: Path) -> bool:
        return self.link_manager.ensure_managed_link(source, target, link_path)

    def _remove_stale_managed_links(
        self, link_path: Path, desired_names: set[str]
    ) -> None:
        self.link_manager.remove_stale_managed_links(link_path, desired_names)

    def _cleanup_link_dir(self, link_path: Path):
        self.link_manager.cleanup_link_dir(link_path)

    def cleanup_skills_link(self, target_link_path: str):
        self.link_manager.cleanup_link_dir((Path.cwd() / target_link_path).absolute())

    def _is_windows_link(self, path: Path) -> bool:
        from core.link_manager import is_windows_link

        return is_windows_link(path)
