"""Setuptools shim that installs CodeAgent's non-Python runtime assets."""

from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).parent
RESOURCE_DIRS = ("prompt", "skills", "hooks", "plugins", "tasks")

# Root-level files that must reach the install tree too. Shipping only the
# directories above left config.example.json out of the wheel, which silently
# disabled config seeding for anyone who pip-installed rather than cloned.
RESOURCE_FILES = ("config.example.json",)


def runtime_data_files() -> list[tuple[str, list[str]]]:
    files: list[Path] = []
    for directory in RESOURCE_DIRS:
        root = ROOT / directory
        if root.exists():
            files.extend(path for path in root.rglob("*") if path.is_file())

    for name in RESOURCE_FILES:
        candidate = ROOT / name
        if candidate.is_file():
            files.append(candidate)

    frontend_dist = ROOT / "web" / "frontend" / "dist"
    if frontend_dist.exists():
        files.extend(path for path in frontend_dist.rglob("*") if path.is_file())

    grouped: dict[str, list[str]] = {}
    for path in files:
        relative = path.relative_to(ROOT)
        destination = (Path("share") / "codeagent" / relative.parent).as_posix()
        grouped.setdefault(destination, []).append(relative.as_posix())
    return sorted(
        (destination, sorted(paths)) for destination, paths in grouped.items()
    )


setup(data_files=runtime_data_files())
