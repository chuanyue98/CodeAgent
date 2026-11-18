#!/usr/bin/env python3
"""
技能打包器 - 创建技能文件夹的可分发 .skill 文件

用法:
    uv run python scripts/package_skill.py <path/to/skill-folder> [output-directory]

示例:
    uv run python scripts/package_skill.py skills/base/my-skill
    uv run python scripts/package_skill.py skills/base/my-skill ./dist
"""

import argparse
import sys
import zipfile
from pathlib import Path

# Emoji in the result banners cannot be encoded by a non-UTF-8 console (cp936
# on a Chinese Windows install, for one), which killed every run with a
# UnicodeEncodeError before it could report anything. Mirrors
# core/console.py; skills run standalone and cannot import it.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
_EXCLUDED_FILE_NAMES = {".DS_Store", "Thumbs.db", ".gitkeep"}
_EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pyd"}


def _validate_skill(skill_path: Path) -> tuple[bool, str]:
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from quick_validate import validate_skill

    return validate_skill(skill_path)


def _should_exclude(file_path: Path, skill_path: Path, skill_filename: Path) -> bool:
    resolved = file_path.resolve()
    if resolved == skill_filename.resolve():
        return True
    rel_parts = file_path.relative_to(skill_path).parts
    if any(part in _EXCLUDED_DIR_NAMES for part in rel_parts[:-1]):
        return True
    if file_path.name in _EXCLUDED_FILE_NAMES or file_path.suffix in _EXCLUDED_SUFFIXES:
        return True
    return False


def package_skill(skill_path, output_dir=None):
    """
    Package a skill folder into a .skill file.

    Args:
        skill_path: Path to the skill folder
        output_dir: Optional output directory for the .skill file (defaults to current directory)

    Returns:
        Path to the created .skill file, or None if error
    """
    skill_path = Path(skill_path).resolve()

    # Validate skill folder exists
    if not skill_path.exists():
        print(f"❌ 错误: 未找到技能文件夹: {skill_path}")
        return None

    if not skill_path.is_dir():
        print(f"❌ 错误: 路径不是目录: {skill_path}")
        return None

    # Validate SKILL.md exists
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        print(f"❌ 错误: 在 {skill_path} 中未找到 SKILL.md")
        return None

    # Run validation before packaging
    print("🔍 正在验证技能...")
    valid, message = _validate_skill(skill_path)
    if not valid:
        print(f"❌ 验证失败: {message}")
        print("   请在打包前修复验证错误。")
        return None
    print(f"✅ {message}\n")

    # Determine output location
    skill_name = skill_path.name
    if output_dir:
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = Path.cwd()

    skill_filename = output_path / f"{skill_name}.skill"

    # Create the .skill file (zip format)
    try:
        with zipfile.ZipFile(skill_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Walk through the skill directory deterministically, excluding caches/junk
            for file_path in sorted(skill_path.rglob("*")):
                if file_path.is_file() and not _should_exclude(
                    file_path, skill_path, skill_filename
                ):
                    arcname = file_path.relative_to(skill_path.parent).as_posix()
                    zipf.write(file_path, arcname)
                    print(f"  已添加: {arcname}")

        print(f"\n✅ 成功将技能打包至: {skill_filename}")
        return skill_filename

    except Exception as e:
        print(f"❌ 创建 .skill 文件时出错: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="验证并将技能文件夹打包为可分发的 .skill 归档文件。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  uv run python scripts/package_skill.py skills/base/my-skill\n"
            "  uv run python scripts/package_skill.py skills/base/my-skill ./dist"
        ),
    )
    parser.add_argument("skill_path", help="技能文件夹路径")
    parser.add_argument("output_dir", nargs="?", default=None, help="可选的输出目录")

    args = parser.parse_args()
    skill_path = args.skill_path
    output_dir = args.output_dir

    print(f"📦 正在打包技能: {skill_path}")
    if output_dir:
        print(f"   输出目录: {output_dir}")
    print()

    result = package_skill(skill_path, output_dir)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
