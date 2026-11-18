from __future__ import annotations

import os
import re
from pathlib import Path

from core.utils.atomic_write import atomic_write

# 不允许空字符串、"."、".." 或以 "." / "-" 开头（防止隐藏文件、路径穿越或被引擎当成命令行参数）。
_SAFE_NAME_RE = re.compile(r"^(?![.-])[\w.-]+$")
_STAGE_GOAL_RE = re.compile(r"\*\*目标(?:\s*[:：]\s*\*\*|\*\*\s*[:：])\s*(.*)")
_STAGE_STATUS_RE = re.compile(r"\*\*状态(?:\s*[:：]\s*\*\*|\*\*\s*[:：])\s*(.*)")
_TAIL_MAX_BYTES = 1024 * 1024


def is_valid_task_name(name: str) -> bool:
    return bool(name and _SAFE_NAME_RE.match(name))


def _tail_lines(path: Path, max_lines: int = 100) -> str:
    """从文件末尾读取最后 ``max_lines`` 行，使用 UTF-8 替换解码。"""
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        read_size = min(size, _TAIL_MAX_BYTES)
        f.seek(size - read_size)
        raw = f.read(read_size)
    text = raw.decode("utf-8", errors="replace")
    return "".join(text.splitlines(keepends=True)[-max_lines:])


class TaskService:
    """管理和读取任务剧本目录的业务服务。"""

    def __init__(self, tasks_root: Path):
        self.tasks_root = tasks_root

    def list_tasks(self) -> list[dict]:
        if not self.tasks_root.exists():
            return []

        tasks = []
        for md_file in sorted(self.tasks_root.glob("*.md")):
            tasks.append(self._parse_task(md_file, full_content=False))
        return tasks

    def create_task(
        self,
        name: str,
        title: str,
        objective: str = "",
        context: str = "",
        instructions: str = "",
        verification: str = "",
    ) -> dict:
        """在任务根目录以独占创建方式写入新的 ``.md`` 任务剧本。"""
        if not is_valid_task_name(name):
            raise ValueError(
                "Task name must match [\\w.-]+ and not start with '.' or '-'"
            )

        self.tasks_root.mkdir(parents=True, exist_ok=True)
        path = self.tasks_root / f"{name}.md"
        if not path.resolve().is_relative_to(self.tasks_root.resolve()):
            raise ValueError("Invalid task name")

        content = (
            f"# {title or name}\n\n"
            f"## Objective (目标)\n{objective}\n\n"
            f"## Context (背景)\n{context}\n\n"
            f"## Instructions (指令)\n{instructions}\n\n"
            f"## Verification (验证)\n{verification}\n"
        )
        try:
            # 独占创建 ("x") 让存在性检查与写入保持原子性，避免并发请求写覆盖。
            with path.open("x", encoding="utf-8") as f:
                f.write(content)
        except FileExistsError as exc:
            raise FileExistsError(f"Task '{name}' already exists") from exc
        return self._parse_task(path, full_content=True)

    def update_task(self, name: str, content: str) -> dict:
        """原子覆盖已存在的任务剧本 Markdown 正文。"""
        if not is_valid_task_name(name):
            raise ValueError(
                "Task name must match [\\w.-]+ and not start with '.' or '-'"
            )

        path = self.tasks_root / f"{name}.md"
        if not path.resolve().is_relative_to(self.tasks_root.resolve()):
            raise ValueError("Invalid task name")
        if not path.is_file():
            raise FileNotFoundError(f"Task '{name}' not found")

        atomic_write(path, content, encoding="utf-8")
        return self._parse_task(path, full_content=True)

    def delete_task(self, name: str) -> bool:
        """删除任务剧本文件；不存在时返回 ``False``。"""
        if not is_valid_task_name(name):
            raise ValueError(
                "Task name must match [\\w.-]+ and not start with '.' or '-'"
            )

        path = self.tasks_root / f"{name}.md"
        if not path.resolve().is_relative_to(self.tasks_root.resolve()):
            raise ValueError("Invalid task name")
        if not path.exists():
            return False
        path.unlink()
        return True

    def get_task(self, name: str, log_path: str | None = None) -> dict | None:
        if not is_valid_task_name(name):
            return None
        path = self.tasks_root / f"{name}.md"
        if not path.resolve().is_relative_to(self.tasks_root.resolve()):
            return None
        if not path.is_file():
            return None

        task_data = self._parse_task(path, full_content=True)

        if log_path and os.path.exists(log_path):
            try:
                task_data["logs"] = _tail_lines(Path(log_path), max_lines=100)
            except Exception:
                task_data["logs"] = "Failed to read logs."

        return task_data

    def _parse_task(self, path: Path, full_content: bool = False) -> dict:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""

        lines = content.splitlines()
        title = path.stem

        # 第一个一级标题作为任务标题
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break

        # 第一个非空且非标题行作为摘要
        description = ""
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped[:120]
                break

        stages = _parse_stages(content)

        result: dict = {
            "name": path.stem,
            "title": title,
            "description": description,
            "hasStages": bool(stages),
            "stages": stages,
        }
        if full_content:
            result["content"] = content
        return result


def _parse_stages(content: str) -> list[dict]:
    stages = []
    sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
    # sections[0] 是首个二级标题之前的前言，不能当作阶段解析。
    for section in sections[1:]:
        if not section.strip():
            continue
        lines = section.splitlines()
        name = lines[0].strip()
        goal = ""
        status = ""
        for line in lines:
            goal_match = _STAGE_GOAL_RE.search(line)
            if goal_match:
                goal = goal_match.group(1).strip()
                continue
            status_match = _STAGE_STATUS_RE.search(line)
            if status_match:
                raw = status_match.group(1).strip()
                status = raw.strip("[]").strip()
        if status or goal:
            stages.append({"name": name, "status": status, "goal": goal})
    return stages
