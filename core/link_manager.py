from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

from core.logging_config import get_logger
from core.utils.atomic_write import atomic_write

LINK_MANIFEST = ".codeagent-links.json"

logger = get_logger(__name__)

_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def is_windows_link(path: Path) -> bool:
    """Verifies if a path is a Windows link or junction point."""
    try:
        if path.is_symlink():
            return True
        if os.name != "nt":
            return False
        if path.is_junction():
            return True
        stat_info = path.lstat()
        attrs = getattr(stat_info, "st_file_attributes", 0)
        return bool(attrs & _FILE_ATTRIBUTE_REPARSE_POINT)
    except Exception:
        return False


class LinkManager:
    """Manages symlink creation, manifest tracking, and cleanup for CodeAgent resources.

    All link operations are tracked via a JSON manifest file (``.codeagent-links.json``)
    placed in the link directory. Only links recorded in the manifest are removed during
    cleanup — user-owned files are never touched.
    """

    def load_manifest(self, link_path: Path) -> dict[str, str]:
        manifest_path = link_path / LINK_MANIFEST
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                result: dict[str, str] = {}
                for name, target in data.items():
                    if not isinstance(name, str) or not isinstance(target, str):
                        continue
                    relative = Path(name)
                    if relative.is_absolute() or ".." in relative.parts:
                        continue
                    result[name] = target
                return result
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Failed to load link manifest from %s: %s", manifest_path, exc
            )
        return {}

    def save_manifest(self, link_path: Path, manifest: dict[str, str]) -> None:
        manifest_path = link_path / LINK_MANIFEST
        if not manifest:
            manifest_path.unlink(missing_ok=True)
            return
        atomic_write(
            manifest_path,
            json.dumps(manifest, indent=2, ensure_ascii=False),
            fsync=True,
        )

    def managed_link_matches(self, path: Path, source: Path) -> bool:
        try:
            if is_windows_link(path) or path.is_symlink():
                return path.resolve() == source.resolve()
            if os.name == "nt" and path.is_file() and source.is_file():
                # 无开发者模式时文件链接可能退化为硬链接或逐字节副本；
                # 只有与源完全一致才认定归属受管，用户改过就保留。
                if os.path.samefile(path, source):
                    return True
                return path.read_bytes() == source.read_bytes()
            return False
        except OSError:
            return False

    def create_skill_link(self, source: Path, target: Path):
        """Creates a symbolic link or Windows junction/link from source to target."""
        try:
            target.symlink_to(source, target_is_directory=source.is_dir())
            return
        except OSError:
            if os.name != "nt":
                raise

        if source.is_dir():
            import _winapi

            _winapi.CreateJunction(str(source), str(target))
            return

        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)

    def safe_remove_link(self, path: Path, *, allow_managed_file: bool = False):
        """Safely removes a link without affecting the target content."""
        if not os.path.lexists(path):
            return

        is_link = is_windows_link(path) or path.is_symlink()
        if not is_link and not (allow_managed_file and path.is_file()):
            logger.warning("Refusing to remove unmanaged path: %s", path)
            return

        try:
            if os.name == "nt":
                lstat_info = path.lstat()
                attrs = getattr(lstat_info, "st_file_attributes", 0)
                is_dir_link = bool(attrs & stat.FILE_ATTRIBUTE_DIRECTORY) or (
                    not is_link and path.is_dir()
                )
                if is_dir_link:
                    os.rmdir(path)
                else:
                    path.unlink(missing_ok=True)
            else:
                path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Security: failed to remove link %s: %s", path, e)

    def ensure_managed_link(self, source: Path, target: Path, link_path: Path) -> bool:
        """Create a link without replacing user-owned files or links."""
        manifest = self.load_manifest(link_path)
        relative_name = target.relative_to(link_path).as_posix()
        previous_source = manifest.get(relative_name)
        resolved_source = str(source.resolve())

        if os.path.lexists(target):
            if self.managed_link_matches(target, source):
                if previous_source != resolved_source:
                    manifest[relative_name] = resolved_source
                    self.save_manifest(link_path, manifest)
                return False
            if previous_source and self.managed_link_matches(
                target, Path(previous_source)
            ):
                self.safe_remove_link(target, allow_managed_file=True)
            else:
                logger.warning("Refusing to replace unmanaged path: %s", target)
                return False

        self.create_skill_link(source, target)
        manifest[relative_name] = resolved_source
        self.save_manifest(link_path, manifest)
        return True

    def remove_stale_managed_links(
        self, link_path: Path, desired_names: set[str]
    ) -> None:
        manifest = self.load_manifest(link_path)
        changed = False
        for relative_name, source in list(manifest.items()):
            if relative_name in desired_names:
                continue
            target = link_path / relative_name
            if self.managed_link_matches(target, Path(source)):
                self.safe_remove_link(target, allow_managed_file=True)
            manifest.pop(relative_name, None)
            changed = True
        if changed:
            self.save_manifest(link_path, manifest)

    def cleanup_link_dir(self, link_path: Path):
        """Remove only links recorded in CodeAgent's ownership manifest."""
        if not link_path.exists():
            return

        try:
            manifest = self.load_manifest(link_path)
            for relative_name, source in manifest.items():
                item = link_path / relative_name
                if self.managed_link_matches(item, Path(source)):
                    self.safe_remove_link(item, allow_managed_file=True)

            self.save_manifest(link_path, {})

            if not any(link_path.iterdir()):
                link_path.rmdir()
        except Exception:
            pass
