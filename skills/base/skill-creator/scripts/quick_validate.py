#!/usr/bin/env python3
"""
技能快速验证脚本 - 最小版本
"""

import re
import sys
from pathlib import Path

import yaml

# Keep verdicts readable on a console whose default encoding isn't UTF-8
# (cp936 on a Chinese Windows install, for one), where the Chinese messages
# below would otherwise come out as mojibake. Mirrors core/console.py; skills
# run standalone from an arbitrary cwd, so they cannot import it.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def validate_skill(skill_path):
    """Basic validation of a skill"""
    skill_path = Path(skill_path)

    # Check SKILL.md exists
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "未找到 SKILL.md"

    # Read and validate frontmatter. SKILL.md is UTF-8 (every one in this repo
    # contains Chinese); without an explicit encoding read_text() falls back to
    # the platform default -- cp936 on a Chinese Windows install -- and dies on
    # a UnicodeDecodeError before validating anything.
    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return False, "未找到 YAML frontmatter"

    # Extract frontmatter
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Frontmatter 格式无效"

    frontmatter_text = match.group(1)

    # Parse YAML frontmatter
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter 必须是 YAML 字典"
    except yaml.YAMLError as e:
        return False, f"Frontmatter 中的 YAML 无效: {e}"

    # Define allowed properties
    ALLOWED_PROPERTIES = {"name", "description", "license", "allowed-tools", "metadata"}

    # Check for unexpected properties (excluding nested keys under metadata)
    unexpected_keys = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected_keys:
        return False, (
            f"SKILL.md frontmatter 中存在意外的键: {', '.join(sorted(unexpected_keys))}. "
            f"允许的属性为: {', '.join(sorted(ALLOWED_PROPERTIES))}"
        )

    # Check required fields
    if "name" not in frontmatter:
        return False, "Frontmatter 中缺少 'name'"
    if "description" not in frontmatter:
        return False, "Frontmatter 中缺少 'description'"

    # Extract name for validation
    name = frontmatter.get("name", "")
    if not isinstance(name, str):
        return False, f"Name 必须是字符串，实际为 {type(name).__name__}"
    name = name.strip()
    if name:
        # Check naming convention (hyphen-case: lowercase with hyphens)
        if not re.match(r"^[a-z0-9-]+$", name):
            return False, f"名称 '{name}' 应为连字符命名法（仅小写字母、数字和连字符）"
        if name.startswith("-") or name.endswith("-") or "--" in name:
            return False, f"名称 '{name}' 不能以连字符开头/结尾或包含连续的连字符"
        # Check name length (max 64 characters per spec)
        if len(name) > 64:
            return False, f"名称太长 ({len(name)} 个字符)。最大为 64 个字符。"

    # Extract and validate description
    description = frontmatter.get("description", "")
    # Checked before the type check: init_skill.py's stub is `[TODO: ...]`,
    # which happens to be valid YAML flow-sequence syntax, so a freshly
    # scaffolded skill failed with "Description 必须是字符串，实际为 list" --
    # that reads as a broken validator rather than "you haven't filled in the
    # template yet". Failing here is still correct; only the wording changes.
    if "TODO" in str(description):
        return False, (
            "Description 仍是 init_skill.py 生成的 TODO 占位符。"
            "请替换为真实描述：说明该技能做什么，以及何时应该触发它。"
        )
    if not isinstance(description, str):
        return False, f"Description 必须是字符串，实际为 {type(description).__name__}"
    description = description.strip()
    if description:
        # Check for angle brackets
        if "<" in description or ">" in description:
            return False, "描述不能包含尖括号 (< 或 >)"
        # Check description length (max 1024 characters per spec)
        if len(description) > 1024:
            return False, f"描述太长 ({len(description)} 个字符)。最大为 1024 个字符。"

    return True, "技能有效！"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python quick_validate.py <skill_directory>")
        sys.exit(1)

    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
