import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import cast

from core.engine_base.environment import EngineExecutionError
from core.logging_config import get_logger
from core.prompt_kit import prompt_general, prompt_review

logger = get_logger(__name__)


class _PromptMixin:
    """Prompt assembly, temp-file lifecycle, and subprocess execution."""

    def assemble_prompt(self, task: str | None = None, is_review: bool = False) -> str:
        """Assembles the final system prompt by combining base prompts and injected groups.

        Args:
            task (str | None): The current task description.
            is_review (bool): Whether to assemble a review-specific prompt.

        Returns:
            str: The assembled prompt string.
        """
        groups = self.get_prompts_to_inject()
        prompt_fn = cast(
            Callable[..., str], prompt_review if is_review else prompt_general
        )

        return prompt_fn(
            task=task,
            groups=groups,
            prompt_root=self.prompt_scanner.prompt_root,
        )

    def write_temp_prompt(self, prompt: str) -> str:
        """Writes the assembled prompt to a temporary file in the project root.

        Args:
            prompt (str): The full prompt string to write.

        Returns:
            str: A guidance message for the agent on how to load the prompt.
        """
        prompt_dir = Path(tempfile.gettempdir()) / "codeagent-prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            dir=prompt_dir, prefix="ca_prompt.", suffix=".tmp", text=True
        )
        temp_file_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(prompt)
        except Exception:
            temp_file_path.unlink(missing_ok=True)
            raise
        if not hasattr(self, "_temp_prompt_paths"):
            self._temp_prompt_paths = set()
        self._temp_prompt_paths.add(temp_file_path)

        abs_path = str(temp_file_path.absolute()).replace("\\", "/")
        read_cmd = "Get-Content" if os.name == "nt" else "cat"

        return (
            f"IMPORTANT: The engineering standards for this session are in the CodeAgent file: {abs_path}. "
            f"Please use your 'run_shell_command' (e.g., '{read_cmd}') to load this file IMMEDIATELY. "
            f"**CRITICAL**: If searching for 'IMPLEMENTATION_PLAN.md' or other core files, be aware they may be listed in '.gitignore'. "
            f"You MUST use 'read_file' directly or set 'no_ignore=true' in search tools to find them."
        )

    def cleanup_temp_prompt(self):
        """Removes temporary prompt files created by this engine instance."""
        paths: set[Path] = getattr(self, "_temp_prompt_paths", set())
        for temp_file_path in list(paths):
            temp_file_path.unlink(missing_ok=True)
            paths.discard(temp_file_path)

    def run_shell(self, cmd: list[str], env: dict):
        """Executes a command in a subprocess with the given environment.

        Args:
            cmd (List[str]): The command and its arguments as a list of strings.
            env (dict): A dictionary of environment variables.

        Raises:
            FileNotFoundError: If the command executable cannot be found.
            EngineExecutionError: If the command returns a non-zero exit code.
        """
        resolved_cmd = list(cmd)
        executable = shutil.which(resolved_cmd[0], path=env.get("PATH"))
        if executable:
            resolved_cmd[0] = executable

        try:
            result = subprocess.run(resolved_cmd, env=env, check=False)
        except FileNotFoundError:
            print(f"❌ Command not found: {cmd[0]}", file=sys.stderr)
            raise

        if result.returncode:
            raise EngineExecutionError(
                f"Engine command failed with exit code {result.returncode}: {cmd[0]}"
            ) from None
