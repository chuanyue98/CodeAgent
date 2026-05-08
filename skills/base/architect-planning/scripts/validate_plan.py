#!/usr/bin/env python3
import re
import sys
from pathlib import Path


def validate_plan(file_path: str):
    path = Path(file_path)
    if not path.exists():
        print(f"Error: {file_path} not found.")
        sys.exit(1)

    content = path.read_text(encoding="utf-8")

    # 定义正则表达式匹配阶段块
    # 匹配 ## 阶段 N: [名称]
    # 以及其后的 **目标**, **成功标准**, **状态**
    phase_pattern = re.compile(
        r"## 阶段 (\d+): (.*?)\n(.*?)(?=\n## 阶段|\Z)", re.DOTALL
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

    for num_str, name, body in phases:
        num = int(num_str)

        # 1. 检查编号连续性
        if num != expected_phase_num:
            errors.append(
                f"Phase {num}: Incorrect numbering. Expected Phase {expected_phase_num}."
            )

        # 2. 检查必需项
        if "**目标**:" not in body:
            errors.append(f"Phase {num}: Missing '**目标**:'.")
        if "**成功标准**:" not in body:
            errors.append(f"Phase {num}: Missing '**成功标准**:'.")
        if "**状态**:" not in body:
            errors.append(f"Phase {num}: Missing '**状态**:'.")
        else:
            # 3. 检查状态合法性
            status_match = re.search(r"\*\*状态\*\*:\s*(.*)", body)
            if status_match:
                status = status_match.group(1).strip()
                if status not in valid_statuses:
                    errors.append(
                        f"Phase {num}: Invalid status '{status}'. Must be one of {valid_statuses}."
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


if __name__ == "__main__":
    # 默认检查根目录下的 IMPLEMENTATION_PLAN.md
    plan_file = "IMPLEMENTATION_PLAN.md"
    validate_plan(plan_file)
