#!/usr/bin/env python3
"""Prompt synthesis toolkit for modular on-demand injection."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable, List

VERSION = "0.2"

EXCLUDED_PROMPT_FILES = {"IMPLEMENTATION_PLAN.md", "README.md"}


def get_prompts_from_directory(directory: Path) -> str:
    """Retrieves and merges all markdown prompt files from a specified directory.

    Args:
        directory: The directory to scan for markdown files.

    Returns:
        A concatenated string of all prompt file contents, separated by double newlines.
    """
    if not directory.exists():
        return ""

    md_files = sorted(directory.glob("*.md"))
    excluded_files = EXCLUDED_PROMPT_FILES

    prompt_parts = []

    for file_path in md_files:
        if file_path.name in excluded_files:
            continue

        try:
            content = file_path.read_text(encoding="utf-8").strip()
            if content:
                prompt_parts.append(content)
                prompt_parts.append("\n\n")
        except OSError:
            continue

    return "".join(prompt_parts).strip()


def prompt_general(
    task: str | None = None,
    groups: List[str] | None = None,
    extra_contents: List[str] | None = None,
    prompt_root: Path | None = None,
) -> str:
    """Synthesizes prompts based on specified groups and task instructions.

    Args:
        task: Specific instructions for the current task.
        groups: List of prompt groups to include (e.g., 'base', 'engineering').
            Defaults to ["base", "engineering", "coding"].
        extra_contents: Additional prompt strings to inject (e.g., from plugins).
        prompt_root: Custom root directory for prompts. If None, uses local 'prompt' dir.

    Returns:
        The fully synthesized prompt string.
    """
    root_dir = Path(__file__).resolve().parent.parent
    if prompt_root is None:
        prompt_root = root_dir / "prompt"

    # Default groups to load
    if groups is None:
        groups = ["base", "engineering", "coding"]

    parts = []

    for group in groups:
        group_dir = prompt_root / group
        content = get_prompts_from_directory(group_dir)
        if content:
            parts.append(f"### {group.capitalize()} Standards ###")
            parts.append(content)
            parts.append("\n\n")

    # Inject extra content (e.g., prompts from plugins)
    if extra_contents:
        for content in extra_contents:
            parts.append(content)
            parts.append("\n\n")

    if task:
        parts.append(f"### CURRENT TASK ###\n{task}")
    else:
        has_novel_group = any(group in {"novel", "fiction"} for group in groups)
        if has_novel_group:
            parts.append(
                "### SYSTEM STATUS: WAITING FOR INSTRUCTION ###\n"
                "You have successfully loaded writing standards.\n"
                "At this stage, please wait for the user's first story request.\n"
                "Do not force engineering workflow checks before the user provides a story task.\n"
                "Confirm you are ready and wait for instructions."
            )
        else:
            parts.append(
                "### SYSTEM STATUS: WAITING FOR INSTRUCTION ###\n"
                "You have successfully loaded engineering standards.\n"
                "**CRITICAL RESTRICTION**: You are currently in 'waiting mode'.\n"
                "1. **MANDATORY**: Check for the existence of `IMPLEMENTATION_PLAN.md` in the current root "
                "directory using `read_file` to confirm if there is an ongoing task.\n"
                "2. Strictly forbidden from using any other tools (e.g., list_directory, grep) to explore the codebase.\n"
                "3. Unless requested by the user, strictly forbidden from summarizing standards or project status.\n"
                "4. Simply confirm you are ready and wait for the user's first instruction."
            )

    return "".join(parts).strip()


def prompt_review(
    task: str | None = None,
    groups: List[str] | None = None,
    prompt_root: Path | None = None,
) -> str:
    """Synthesizes code review prompts by including the 'review' group.

    Args:
        task: Specific instructions for the review task.
        groups: List of prompt groups to include. Defaults to full engineering and review context.
        prompt_root: Custom root directory for prompts.

    Returns:
        The fully synthesized review prompt string.
    """
    if groups is None:
        # Review tasks usually require full context
        groups = ["base", "engineering", "coding", "web", "review"]

    return prompt_general(task=task, groups=groups, prompt_root=prompt_root)


def parse_args(
    choices: list[str],
    arguments: list[str],
) -> tuple[argparse.Namespace, argparse.ArgumentParser]:
    """Parses command-line arguments for the prompt toolkit.

    Args:
        choices: List of available prompt template names.
        arguments: List of command-line arguments to parse.

    Returns:
        A tuple containing the parsed arguments and the argument parser object.
    """
    parser = argparse.ArgumentParser(
        description="Prompt Toolkit CLI (Modular Architecture)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-p",
        "--prompt",
        choices=choices,
        default="general",
        help="Select the prompt template type",
    )
    parser.add_argument(
        "-g",
        "--groups",
        nargs="+",
        help="Inject prompt groups on-demand (e.g., base web engineering)",
    )
    parser.add_argument(
        "-t",
        "--task",
        type=str,
        help="Specific task instructions",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {VERSION}"
    )

    return parser.parse_args(arguments), parser


def main() -> None:
    """Main entry point for the command-line interface."""
    import sys

    prompts: dict[str, Callable[..., str]] = {
        "general": prompt_general,
        "review": prompt_review,
    }

    parsed_args, parser = parse_args(list(prompts.keys()), sys.argv[1:])

    prompt_fn = prompts[parsed_args.prompt]
    print(prompt_fn(task=parsed_args.task, groups=parsed_args.groups))


if __name__ == "__main__":
    main()
