from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


LINK_MANIFEST = ".codeagent-links.json"


def is_windows_link(path: Path) -> bool:
    """Verifies if a path is a Windows link or junction point."""
    try:
        if path.is_symlink():
            return True

        stat_info = path.lstat()
        attrs = getattr(stat_info, "st_file_attributes", 0)
        is_reparse = bool(attrs & 1024)

        if is_reparse:
            return True

        if path.is_mount():
            return True

        return False
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
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def save_manifest(self, link_path: Path, manifest: dict[str, str]) -> None:
        manifest_path = link_path / LINK_MANIFEST
        if not manifest:
            manifest_path.unlink(missing_ok=True)
            return
        link_path.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            dir=link_path, prefix=".codeagent-links.", suffix=".tmp", text=True
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, manifest_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def managed_link_matches(self, path: Path, source: Path) -> bool:
        try:
            return (
                is_windows_link(path) or path.is_symlink()
            ) and path.resolve() == source.resolve()
        except OSError:
            return False

    def create_skill_link(self, source: Path, target: Path):
        """Creates a symbolic link or Windows junction from source to target."""
        try:
            target.symlink_to(source, target_is_directory=source.is_dir())
            return
        except OSError:
            if os.name != "nt" or not source.is_dir():
                raise

        subprocess.run(
            ["cmd", "/c", "mklink", "/j", str(target), str(source)],
            capture_output=True,
            check=True,
        )

    def safe_remove_link(self, path: Path):
        """Safely removes a link without affecting the target content."""
        if not path.exists() and not path.is_symlink():
            return

        if not (is_windows_link(path) or path.is_symlink()):
            print(f"⚠️ Refusing to remove unmanaged path: {path}")
            return

        try:
            if os.name == "nt":
                if path.is_dir():
                    subprocess.run(
                        ["cmd", "/c", "rmdir", str(path)],
                        capture_output=True,
                        check=False,
                    )
                else:
                    path.unlink(missing_ok=True)
            else:
                path.unlink(missing_ok=True)
        except Exception as e:
            print(f"⚠️ Security: Failed to remove link {path}: {e}")

    def ensure_managed_link(self, source: Path, target: Path, link_path: Path) -> bool:
        """Create a link without replacing user-owned files or links."""
        manifest = self.load_manifest(link_path)
        relative_name = target.relative_to(link_path).as_posix()
        previous_source = manifest.get(relative_name)

        if target.exists() or target.is_symlink():
            if self.managed_link_matches(target, source):
                if previous_source is not None:
                    manifest[relative_name] = str(source.resolve())
                    self.save_manifest(link_path, manifest)
                return False
            if previous_source and self.managed_link_matches(
                target, Path(previous_source)
            ):
                self.safe_remove_link(target)
            else:
                print(f"⚠️ Refusing to replace unmanaged path: {target}")
                return False

        self.create_skill_link(source, target)
        manifest[relative_name] = str(source.resolve())
        self.save_manifest(link_path, manifest)
        return True

    def remove_stale_managed_links(
        self, link_path: Path, desired_names: set[str]
    ) -> None:
        manifest = self.load_manifest(link_path)
        for relative_name, source in list(manifest.items()):
            if relative_name in desired_names:
                continue
            target = link_path / relative_name
            if self.managed_link_matches(target, Path(source)):
                self.safe_remove_link(target)
            manifest.pop(relative_name, None)
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
                    self.safe_remove_link(item)

            self.save_manifest(link_path, {})

            if not any(link_path.iterdir()):
                link_path.rmdir()
        except Exception:
            pass
