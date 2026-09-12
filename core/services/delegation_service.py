"""Cross-engine delegation and git worktree isolation service.

Provides:
- ``isolated_worktree``: A context manager creating an isolated Git worktree on a temporary branch
  so that worker engines can make edits and test without touching the host's working tree.
- ``delegate_subtask``: Runs a subtask using a specified engine non-interactively, capturing
  execution output, modified files, git diff, and branch reference.
- ``handoff_session``: Converts an active or recent session to a target engine format and returns
  resume instructions.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.engine_registry import ENGINES, get_spec, normalize_engine_name
from core.host_env import child_environ
from core.logging_config import get_logger
from core.resource_locator import CODE_ROOT

logger = get_logger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 300
_GIT_TIMEOUT_SECONDS = 30


@dataclass
class DelegationResult:
    """Result of delegating a subtask to an engine."""

    success: bool
    engine: str
    instruction: str
    exit_code: int
    output: str
    files_changed: list[str] = field(default_factory=list)
    diff: str = ""
    branch: str | None = None
    isolated_worktree: bool = False
    duration_seconds: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_summary(self) -> str:
        status_str = "SUCCESS" if self.success else f"FAILED (exit {self.exit_code})"
        lines = [
            f"### Subtask Delegation: [{self.engine.upper()}] — {status_str}",
            f"- **Duration**: {self.duration_seconds:.1f}s",
        ]
        if self.isolated_worktree and self.branch:
            lines.append(f"- **Isolated Branch**: `{self.branch}`")
        if self.files_changed:
            lines.append(f"- **Files Changed** ({len(self.files_changed)}):")
            for f in self.files_changed[:10]:
                lines.append(f"  - `{f}`")
            if len(self.files_changed) > 10:
                lines.append(f"  - ...and {len(self.files_changed) - 10} more")
        if self.error:
            lines.append(f"\n**Error**: {self.error}")

        if self.diff:
            diff_preview = self.diff[:3000]
            truncated = " ... (diff truncated)" if len(self.diff) > 3000 else ""
            lines.append(f"\n```diff\n{diff_preview}{truncated}\n```")

        if self.output:
            tail_lines = self.output.strip().splitlines()[-25:]
            lines.append("\n<details><summary>Execution Output Tail (25 lines)</summary>\n\n```\n" + "\n".join(tail_lines) + "\n```\n</details>")

        return "\n".join(lines)


def is_git_repo(path: Path) -> bool:
    """Returns True if *path* is inside a valid git repository working tree."""
    if shutil.which("git") is None:
        return False
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"
    except (subprocess.SubprocessError, OSError):
        return False


def get_git_root(path: Path) -> Path:
    """Returns the top-level directory of the git repository containing *path*."""
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    return Path(proc.stdout.strip()).resolve()


@contextmanager
def isolated_worktree(
    workspace: Path,
    branch_prefix: str = "ca/worker",
) -> Iterator[dict[str, Any]]:
    """Context manager for running work in an isolated git worktree.

    If *workspace* is a git repository, adds a temporary worktree under
    ``.ca_worktrees/`` on a new branch derived from *branch_prefix*.

    Yields:
        dict:
            - ``"path"``: Path to the working directory (worktree if isolated, original workspace otherwise).
            - ``"isolated"``: bool indicating whether worktree isolation was activated.
            - ``"branch"``: str branch name if isolated, else None.
            - ``"repo_root"``: Path to repo root if isolated, else None.
    """
    ws = workspace.resolve()
    if not is_git_repo(ws):
        yield {"path": ws, "isolated": False, "branch": None, "repo_root": None}
        return

    repo_root = get_git_root(ws)
    branch = f"{branch_prefix}-{int(time.time())}-{os.urandom(3).hex()}"
    worktree_parent = repo_root / ".ca_worktrees"
    worktree_parent.mkdir(parents=True, exist_ok=True)
    worktree_dir = worktree_parent / branch.replace("/", "_")

    created = False
    try:
        add_proc = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "add", str(worktree_dir), "-b", branch],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
        if add_proc.returncode != 0:
            logger.warning(
                "Failed to create git worktree: %s. Falling back to in-place workspace.",
                add_proc.stderr.strip(),
            )
            yield {"path": ws, "isolated": False, "branch": None, "repo_root": None}
            return

        created = True
        yield {
            "path": worktree_dir,
            "isolated": True,
            "branch": branch,
            "repo_root": repo_root,
        }

    finally:
        if created and worktree_dir.exists():
            # Check for changes in worktree
            status_proc = subprocess.run(
                ["git", "-C", str(worktree_dir), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SECONDS,
            )
            has_changes = bool(status_proc.stdout.strip())

            # Check if commits were added on the branch compared to repo_root HEAD
            log_proc = subprocess.run(
                ["git", "-C", str(repo_root), "rev-list", f"HEAD..{branch}"],
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SECONDS,
            )
            has_commits = bool(log_proc.stdout.strip())

            if has_changes:
                # Stage and commit any uncommitted changes so the worker branch preserves them
                subprocess.run(
                    ["git", "-C", str(worktree_dir), "add", "-A"],
                    capture_output=True,
                    timeout=_GIT_TIMEOUT_SECONDS,
                )
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(worktree_dir),
                        "commit",
                        "-m",
                        f"ca: subtask commit on {branch}",
                    ],
                    capture_output=True,
                    timeout=_GIT_TIMEOUT_SECONDS,
                )
                has_commits = True

            # Clean up the worktree
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "remove", "--force", str(worktree_dir)],
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SECONDS,
            )

            # If no commits were produced, delete the empty temporary branch
            if not has_commits:
                subprocess.run(
                    ["git", "-C", str(repo_root), "branch", "-D", branch],
                    capture_output=True,
                    timeout=_GIT_TIMEOUT_SECONDS,
                )


def _collect_git_changes(
    path: Path, base_commit: str | None = None
) -> tuple[list[str], str]:
    """Collects changed files and git diff for *path*."""
    if not is_git_repo(path):
        return [], ""
    try:
        # Porcelain status
        status_proc = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
        files = [
            line[3:].strip()
            for line in status_proc.stdout.splitlines()
            if len(line) > 3
        ]

        # Diff against base commit if available, else HEAD
        ref = base_commit if base_commit else "HEAD"
        diff_proc = subprocess.run(
            ["git", "-C", str(path), "diff", ref],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
        diff = diff_proc.stdout
        return files, diff
    except Exception as exc:
        logger.warning("Failed to collect git changes: %s", exc)
        return [], ""


def delegate_subtask(
    engine: str,
    instruction: str,
    workspace: Path | str | None = None,
    target_paths: list[str] | None = None,
    timeout: int = _DEFAULT_TIMEOUT_SECONDS,
    isolate: bool = True,
    group: str = "common",
    root_dir: Path | None = None,
) -> DelegationResult:
    """Delegates an isolated subtask to another engine.

    Args:
        engine: Target engine (claude, codex, opencode, antigravity, codebuddy).
        instruction: Clear instructions and acceptance criteria for the subtask.
        workspace: Project directory to execute in (default: current working directory).
        target_paths: Optional list of files or folders the subtask focuses on.
        timeout: Maximum execution timeout in seconds.
        isolate: Whether to run in an isolated Git worktree (if in a Git repo).
        group: Resource group to mount (default: "common").
        root_dir: CodeAgent repository root directory.

    Returns:
        DelegationResult with exit code, outputs, diff, and branch details.
    """
    canonical_engine = normalize_engine_name(engine)
    if canonical_engine not in ENGINES:
        return DelegationResult(
            success=False,
            engine=engine,
            instruction=instruction,
            exit_code=1,
            output="",
            error=f"Unknown engine: {engine!r}. Supported engines: {sorted(ENGINES)}",
        )

    if not instruction or not instruction.strip():
        return DelegationResult(
            success=False,
            engine=canonical_engine,
            instruction="",
            exit_code=1,
            output="",
            error="Instruction must not be empty.",
        )

    root = root_dir or CODE_ROOT
    ws = Path(workspace).resolve() if workspace else Path.cwd().resolve()
    spec = get_spec(canonical_engine)
    if spec is None:
        return DelegationResult(
            success=False,
            engine=canonical_engine,
            instruction=instruction,
            exit_code=1,
            output="",
            error=f"No engine spec found for {canonical_engine}",
        )

    target_script = root / "engines" / spec.launch_script
    if not target_script.is_file():
        return DelegationResult(
            success=False,
            engine=canonical_engine,
            instruction=instruction,
            exit_code=1,
            output="",
            error=f"Launch script not found: {target_script}",
        )

    # Prepend target paths hint if specified
    prompt_parts = []
    if target_paths:
        prompt_parts.append("Target files / context:")
        for p in target_paths:
            prompt_parts.append(f"- {p}")
        prompt_parts.append("")
    prompt_parts.append(instruction.strip())
    full_prompt = "\n".join(prompt_parts)

    worktree_ctx = (
        isolated_worktree(ws)
        if isolate
        else contextmanager(lambda: (yield {"path": ws, "isolated": False, "branch": None, "repo_root": None}))()
    )

    t0 = time.time()
    try:
        with worktree_ctx as ctx:
            effective_dir = ctx["path"]
            isolated = ctx["isolated"]
            branch = ctx["branch"]

            # Record base commit if in git repo
            base_commit = None
            if is_git_repo(effective_dir):
                try:
                    res = subprocess.run(
                        ["git", "-C", str(effective_dir), "rev-parse", "HEAD"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if res.returncode == 0:
                        base_commit = res.stdout.strip()
                except Exception:
                    pass

            env = child_environ()
            env["CA_PROJECT_GROUP"] = group
            env["CA_YOLO"] = "1"

            cmd = [
                sys.executable,
                str(target_script),
                "-y",
                "--non-interactive",
                full_prompt,
            ]

            proc = subprocess.run(
                cmd,
                cwd=str(effective_dir),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )

            duration = time.time() - t0
            output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
            files_changed, diff = _collect_git_changes(effective_dir, base_commit)

            return DelegationResult(
                success=proc.returncode == 0,
                engine=canonical_engine,
                instruction=instruction,
                exit_code=proc.returncode,
                output=output,
                files_changed=files_changed,
                diff=diff,
                branch=branch,
                isolated_worktree=isolated,
                duration_seconds=duration,
                error=None if proc.returncode == 0 else f"Process exited with code {proc.returncode}",
            )

    except subprocess.TimeoutExpired:
        duration = time.time() - t0
        return DelegationResult(
            success=False,
            engine=canonical_engine,
            instruction=instruction,
            exit_code=124,
            output="",
            duration_seconds=duration,
            error=f"Delegation subtask timed out after {timeout} seconds",
        )
    except Exception as exc:
        duration = time.time() - t0
        return DelegationResult(
            success=False,
            engine=canonical_engine,
            instruction=instruction,
            exit_code=1,
            output="",
            duration_seconds=duration,
            error=f"Delegation failed: {exc}",
        )


def handoff_session(
    target_engine: str,
    source_engine: str | None = None,
    session_id: str | None = None,
    project_path: str | Path | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """Converts a session to target_engine and reports resume command and metadata.

    Args:
        target_engine: Target engine to convert session into.
        source_engine: Source engine (auto-resolved if None).
        session_id: Source session id (resolves latest if None).
        project_path: Project directory (defaults to cwd).
        reason: Optional handoff reason (e.g. rate limit, stuck loop).

    Returns:
        dict with status, target_engine, new_session_id, resume_command, and message.
    """
    canonical_target = normalize_engine_name(target_engine)
    if canonical_target not in ENGINES:
        raise ValueError(
            f"Unknown target engine: {target_engine!r}. Supported: {sorted(ENGINES)}"
        )

    ws = str(Path(project_path).resolve() if project_path else Path.cwd().resolve())

    from core.cli.session_select import SessionSelectorError, resolve_session
    from core.services.resume_commands import resume_command
    from core.session_history import repository
    from core.session_history.writers import write_session

    resolved_source = normalize_engine_name(source_engine) if source_engine else None
    resolved_id = session_id

    if not resolved_id or resolved_id == "latest":
        try:
            resolved = resolve_session(None, ws, engine=resolved_source)
            resolved_id = resolved.session_id
            if not resolved_source:
                resolved_source = resolved.engine
        except SessionSelectorError as exc:
            raise ValueError(f"No source session found in {ws}: {exc}") from exc

    if not resolved_source:
        resolved_source = "claude"  # fallback default

    session = repository.get_full(resolved_source, resolved_id, ws)
    if not session:
        raise ValueError(f"Source session not found: {resolved_source}:{resolved_id}")

    new_id = write_session(session, canonical_target)
    cmd = resume_command(canonical_target, new_id, Path(ws))

    return {
        "status": "ready",
        "source_engine": resolved_source,
        "target_engine": canonical_target,
        "original_session_id": resolved_id,
        "new_session_id": new_id,
        "resume_command": " ".join(cmd),
        "reason": reason,
        "message": (
            f"Session {resolved_id} successfully converted to {canonical_target} "
            f"(new session id: {new_id}). Continue with: {' '.join(cmd)}"
        ),
    }
