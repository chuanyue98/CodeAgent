"""Shell:first prelaunch command handling for Codex engine.

Allows prompts/tasks/code-plans to define prelaunch shell commands with
safe confirmation gates and override checks.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

SHELL_FIRST_MARKER = "```shell:first"
SHELL_FIRST_ALLOW_ENV = "CODEAGENT_ALLOW_SHELL_FIRST"


def extract_shell_first_blocks(text: str) -> tuple[str, list[str]]:
    """Extract and remove shell:first blocks, returning text and commands."""
    if not text:
        return text, []

    commands: list[str] = []
    lines = text.splitlines()
    sanitized_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.strip() == SHELL_FIRST_MARKER:
            i += 1
            block_lines: list[str] = []
            while i < len(lines) and lines[i].strip() != "```":
                block_lines.append(lines[i])
                i += 1
            if i == len(lines):
                sanitized_lines.append(line)
                sanitized_lines.extend(block_lines)
                break
            script = "\n".join(block_lines).strip()
            if script:
                commands.append(script)
            i += 1
            continue

        sanitized_lines.append(line)
        i += 1

    sanitized = "\n".join(sanitized_lines).strip()
    return sanitized, commands


def _shell_first_allowed_via_override() -> bool:
    """Checks the explicit opt-in env var that skips the shell:first confirmation gate."""
    return os.environ.get(SHELL_FIRST_ALLOW_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _resolve_shell(env: dict) -> tuple[str, list[str]] | None:
    """Finds the shell for one shell:first command; ``None`` if none exists.

    参数风格跟着解析到的二进制走，而不是跟着操作系统走：Windows 上虽然优先
    找 pwsh/powershell，但 which 完全可能解析出 Git Bash 的 bash —— 给
    bash 塞 PowerShell 参数是必然失败的，反之亦然。
    """
    path = env.get("PATH")
    candidates = (
        ("pwsh", "powershell", "bash", "sh") if os.name == "nt" else ("bash", "sh")
    )
    for name in candidates:
        found = shutil.which(name, path=path)
        if not found:
            continue
        binary = Path(found).stem.lower()
        if binary in ("pwsh", "powershell"):
            return found, [found, "-NoProfile", "-Command"]
        if binary == "bash":
            return found, [found, "-lc"]
        return found, [found, "-c"]
    return None


def run_prelaunch_commands(
    commands: list[str],
    env: dict,
    codex_non_interactive: bool = False,
    allow_override: bool | None = None,
) -> None:
    """Run shell:first commands before invoking Codex.

    These commands come from markdown text (prompts/tasks/code plans) that may
    originate from shared files, downloaded skills, or marketplace plugins --
    not necessarily something the current user wrote or reviewed. This must
    never execute silently:

    - Non-interactive / no-TTY sessions fail closed: they refuse to run
      shell:first commands unless ``SHELL_FIRST_ALLOW_ENV`` is explicitly set.
    - Interactive sessions print the full command text and require a "y"
      confirmation before each command runs.
    """
    if not commands:
        return

    allow_override = (
        _shell_first_allowed_via_override()
        if allow_override is None
        else allow_override
    )
    interactive = (
        sys.stdin.isatty() and sys.stdout.isatty() and not codex_non_interactive
    )

    print()
    print(
        "⚠️  This prompt/task/code-plan file contains 'shell:first' "
        "command(s) that would run automatically on this machine before "
        "Codex launches."
    )
    print(
        "⚠️  Only proceed if you trust where this file came from -- "
        "shared code plans, skills, and plugins can embed arbitrary shell "
        "commands."
    )

    if not interactive and not allow_override:
        print(
            "❌ Refusing to run shell:first commands in a non-interactive "
            f"session. Re-run interactively, or set {SHELL_FIRST_ALLOW_ENV}=1 "
            "(or pass --allow-shell-first) to explicitly allow this.",
            file=sys.stderr,
        )
        for script in commands:
            command = script.strip()
            if not command:
                continue
            preview = command.splitlines()[0]
            suffix = " ..." if "\n" in command else ""
            print(f"    would run: {preview}{suffix}", file=sys.stderr)
        sys.exit(1)

    if allow_override:
        print(
            f"✅ {SHELL_FIRST_ALLOW_ENV} override active -- running "
            "shell:first commands without per-command confirmation."
        )

    for script in commands:
        command = script.strip()
        if not command:
            continue

        print("----- shell:first command -----")
        print(command)
        print("--------------------------------")

        if interactive and not allow_override:
            answer = input("Run this command? [y/N]: ").strip().lower()
            if answer not in ("y", "yes"):
                print("Skipped by user.")
                continue

        preview = command.splitlines()[0]
        suffix = " ..." if "\n" in command else ""
        print(f"Running prelaunch command: {preview}{suffix}")

        try:
            resolved = _resolve_shell(env)
            if resolved is None:
                print(
                    "No suitable shell (pwsh/powershell/bash/sh) found for shell:first",
                    file=sys.stderr,
                )
                sys.exit(1)
            _shell, shell_args = resolved
            subprocess.run(
                [*shell_args, command],
                check=True,
                env=env,
            )
        except subprocess.CalledProcessError as exc:
            print(f"Prelaunch command failed: {exc}", file=sys.stderr)
            sys.exit(1)
