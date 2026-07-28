import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

from core.logging_config import get_logger

if TYPE_CHECKING:
    from core.link_manager import LinkManager
    from core.lock_manager import LockManager

logger = get_logger(__name__)


class _LinksMixin:
    """Resource locking passthrough and skills/plugins symlink management."""

    # Provided by BaseEngine.__init__ / _ConfigMixin.
    if TYPE_CHECKING:
        lock_manager: "LockManager"
        link_manager: "LinkManager"

        def get_current_project_group(self) -> str: ...
        def get_skills_to_mount(self) -> list[str]: ...
        def get_plugins_to_mount(self) -> list[dict[str, Any]]: ...
        def _get_skill_search_roots(self) -> list[Path]: ...

    def acquire_resource_lock(self, lock_path: Path) -> BinaryIO:
        return self.lock_manager.acquire_resource_lock(lock_path)

    def release_resource_lock(self, handle: BinaryIO) -> None:
        self.lock_manager.release_resource_lock(handle)

    def ensure_skills_link(self, target_link_path: str):
        link_path = (Path.cwd() / target_link_path).absolute()

        skills_to_mount = self.get_skills_to_mount()
        if not skills_to_mount:
            self.link_manager.cleanup_link_dir(link_path)
            return

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
            self.link_manager.cleanup_link_dir(link_path)
            return

        logger.info(
            "Skills matched group: [%s] (匹配 %d 个根目录，挂载 %d 个技能)",
            self.get_current_project_group(),
            len(skills_to_mount),
            len(resolved_skills),
        )
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
        - Gemini:   ~/.gemini/extensions/
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
        if not path.exists() and not path.is_symlink():
            return

        if not (self._is_windows_link(path) or path.is_symlink()):
            logger.warning("Refusing to remove unmanaged path: %s", path)
            return

        try:
            if os.name == "nt":
                if path.is_dir():
                    result = subprocess.run(
                        ["cmd", "/c", "rmdir", str(path)],
                        capture_output=True,
                        check=False,
                    )
                    if result.returncode != 0:
                        detail = (
                            result.stderr.decode(errors="replace").strip()
                            or result.stdout.decode(errors="replace").strip()
                            or f"rmdir exited with code {result.returncode}"
                        )
                        logger.warning(
                            "Security: Failed to remove link %s: %s", path, detail
                        )
                else:
                    path.unlink(missing_ok=True)
            else:
                path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Security: Failed to remove link %s: %s", path, e)

    _LINK_MANIFEST = ".codeagent-links.json"

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
