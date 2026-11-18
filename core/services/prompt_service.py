from pathlib import Path

from core.prompt_scanner import EXCLUDED_PROMPT_FILES, PromptScanner


class PromptService:
    """管理和扫描提示词模板的业务服务。"""

    def __init__(self, prompts_root: Path, root_dir: Path | None = None):
        """使用提示词根目录和可选项目根目录初始化 ``PromptService``。

        Args:
            prompts_root: 提示词分组根目录。
            root_dir: 可选项目根目录，保留以兼容三参调用方。
        """
        self.prompts_root = prompts_root
        self.root_dir = root_dir
        self.scanner = PromptScanner(prompts_root)

    def get_prompt_groups(self) -> list[dict]:
        """复用扫描器结果按分组聚合提示词文件详情。"""
        scanned, _ = self.scanner.scan()
        prompt_groups = []

        for category in sorted(scanned.keys()):
            group_dir = self.prompts_root / category
            files = []
            combined_parts = []
            description = ""

            for prompt_name in sorted(scanned[category]):
                prompt_file = group_dir / f"{prompt_name}.md"
                if prompt_file.name in EXCLUDED_PROMPT_FILES:
                    continue
                try:
                    content = prompt_file.read_text(
                        encoding="utf-8", errors="replace"
                    ).strip()
                except (OSError, UnicodeDecodeError):
                    continue
                if not content:
                    continue

                files.append(
                    {
                        "name": prompt_file.stem,
                        "path": str(prompt_file.resolve().as_posix()),
                    }
                )
                combined_parts.append(f"## {prompt_file.stem}\n\n{content}")

                if not description:
                    for line in content.splitlines():
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#"):
                            description = stripped
                            break

            prompt_groups.append(
                {
                    "id": category,
                    "name": category,
                    "description": description
                    or f"{len(files)} prompt files in '{category}'",
                    "readme": "\n\n".join(combined_parts),
                    "files": files,
                }
            )
        return prompt_groups
