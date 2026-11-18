#!/usr/bin/env python3
"""校验 IMPLEMENTATION_PLAN.md 是否符合阶段划分与状态跟踪格式。"""

import argparse
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def validate_plan(file_path: str):
    path = Path(file_path)
    if not path.is_file():
        print(f"Error: {file_path} not found.")
        sys.exit(1)

    content = path.read_text(encoding="utf-8", errors="replace")

    # 匹配行首 ## 阶段 N: [名称] 以及其后的阶段正文，直到下一个 ## 标题或文件结尾
    phase_pattern = re.compile(
        r"^##\s+阶段\s+(\d+)\s*[:：]\s*([^\n]*)(?:\n(.*?))?(?=\n##\s+|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    phases = phase_pattern.findall(content)

    if not phases:
        print(
            "Error: No phases found in IMPLEMENTATION_PLAN.md. Please follow the template."
        )
        sys.exit(1)

    errors = []
    expected_phase_num = 1
    valid_statuses = {"未开始", "进行中", "已完成"}

    for num_str, _name, body in phases:
        num = int(num_str)

        # 1. 检查编号连续性
        if num != expected_phase_num:
            errors.append(
                f"Phase {num}: Incorrect numbering. Expected Phase {expected_phase_num}."
            )

        # 2. 检查必需项
        if not re.search(r"\*\*目标\*\*\s*[:：]", body):
            errors.append(f"Phase {num}: Missing '**目标**:'.")
        if not re.search(r"\*\*成功标准\*\*\s*[:：]", body):
            errors.append(f"Phase {num}: Missing '**成功标准**:'.")
        if not re.search(r"\*\*状态\*\*\s*[:：]", body):
            errors.append(f"Phase {num}: Missing '**状态**:'.")
        else:
            # 3. 检查状态合法性
            status_match = re.search(r"\*\*状态\*\*\s*[:：]\s*(.*)", body)
            if status_match:
                status = status_match.group(1).strip().strip("`").strip()
                if status not in valid_statuses:
                    errors.append(
                        f"Phase {num}: Invalid status '{status}'. Must be one of {sorted(valid_statuses)}."
                    )
            else:
                errors.append(f"Phase {num}: Could not parse status value.")

        expected_phase_num += 1

    if errors:
        print("Validation failed with following errors:")
        for err in errors:
            print(f"- {err}")
        sys.exit(1)

    print("Success: IMPLEMENTATION_PLAN.md is valid.")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="校验 IMPLEMENTATION_PLAN.md 的阶段编号、必需字段与状态值。"
    )
    parser.add_argument(
        "plan_file",
        nargs="?",
        default="IMPLEMENTATION_PLAN.md",
        help="待校验的计划文件路径（默认为当前目录的 IMPLEMENTATION_PLAN.md）",
    )
    args = parser.parse_args()
    validate_plan(args.plan_file)


if __name__ == "__main__":
    main()
