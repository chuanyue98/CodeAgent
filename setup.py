"""Setuptools shim that installs CodeAgent's non-Python runtime assets."""

import sys
from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).parent
RESOURCE_DIRS = ("prompt", "skills", "hooks", "plugins", "tasks")

#: Commands that produce a distribution someone else installs. Editable and
#: metadata-only commands are excluded: `uv sync` on a fresh clone runs before
#: anyone has had a chance to build the frontend, and `ca ui` already explains
#: the missing bundle at that point.
DISTRIBUTION_COMMANDS = ("bdist_wheel", "sdist", "bdist_egg")

# Root-level files that must reach the install tree too. Shipping only the
# directories above left config.example.json out of the wheel, which silently
# disabled config seeding for anyone who pip-installed rather than cloned.
RESOURCE_FILES = ("config.example.json",)

# 仅排除缓存、VCS 与系统临时文件；不能一刀切过滤所有点开头目录，
# 因为插件（如 superpowers）会在 `.claude-plugin/`、`.codex-plugin/` 等隐藏目录
# 中存放必需的清单文件。
_EXCLUDED_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".git",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
    }
)
_EXCLUDED_FILE_NAMES = frozenset({".git", ".gitkeep", ".DS_Store", "Thumbs.db"})
_EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo", ".pyd", ".tmp"})


def _is_excluded_asset(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    if any(part in _EXCLUDED_DIR_NAMES for part in rel_parts[:-1]):
        return True
    return path.name in _EXCLUDED_FILE_NAMES or path.suffix in _EXCLUDED_SUFFIXES


def _building_a_distribution() -> bool:
    return any(command in sys.argv for command in DISTRIBUTION_COMMANDS)


def runtime_data_files() -> list[tuple[str, list[str]]]:
    files: list[Path] = []
    for directory in RESOURCE_DIRS:
        root = ROOT / directory
        if root.exists():
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file() and not _is_excluded_asset(path, root)
            )

    for name in RESOURCE_FILES:
        candidate = ROOT / name
        if candidate.is_file():
            files.append(candidate)

    frontend_dist = ROOT / "web" / "frontend" / "dist"
    if frontend_dist.exists():
        files.extend(
            path
            for path in frontend_dist.rglob("*")
            if path.is_file() and not _is_excluded_asset(path, frontend_dist)
        )
    elif _building_a_distribution():
        # Shipping a wheel without the bundle installs cleanly and then fails
        # at `ca ui`, on a machine that has no frontend toolchain to fix it.
        raise SystemExit(
            "error: web/frontend/dist is missing, so this build would ship a "
            "wheel with no Web UI.\n"
            "Build the frontend first:\n"
            "  cd web/frontend && bun install && bun run build\n"
            "(or: npm install && npm run build)"
        )

    grouped: dict[str, list[str]] = {}
    for path in files:
        relative = path.relative_to(ROOT)
        destination = (Path("share") / "codeagent" / relative.parent).as_posix()
        grouped.setdefault(destination, []).append(relative.as_posix())
    return sorted(
        (destination, sorted(paths)) for destination, paths in grouped.items()
    )


setup(data_files=runtime_data_files())
