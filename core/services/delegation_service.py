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
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.delegation_depth import DEPTH_ENV, current_depth
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
            lines.append(
                "\n<details><summary>Execution Output Tail (25 lines)</summary>\n\n```\n"
                + "\n".join(tail_lines)
                + "\n```\n</details>"
            )

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
    *,
    carry_changes: bool = False,
    keep: bool = True,
) -> Iterator[dict[str, Any]]:
    """Context manager for running work in an isolated git worktree.

    If *workspace* is a git repository, adds a temporary worktree under
    ``.ca_worktrees/`` on a new branch derived from *branch_prefix*.

    ``carry_changes`` 把主工作区尚未提交的改动带进 worktree（review 要审的
    正是这些）；``keep=False`` 时用完连同分支一起删掉，不留任何痕迹。

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
            [
                "git",
                "-C",
                str(repo_root),
                "worktree",
                "add",
                str(worktree_dir),
                "-b",
                branch,
            ],
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
        if carry_changes:
            _carry_uncommitted_changes(repo_root, worktree_dir)
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

            if not keep:
                has_changes = has_commits = False
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
                [
                    "git",
                    "-C",
                    str(repo_root),
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree_dir),
                ],
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

            # 最后一个 worktree 用完，别在用户仓库里留一个空的 .ca_worktrees/。
            try:
                worktree_parent.rmdir()
            except OSError:
                pass


def _carry_uncommitted_changes(repo_root: Path, worktree_dir: Path) -> None:
    """把主工作区相对 HEAD 的改动（含已暂存）原样打到 worktree 上。"""
    diff = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "HEAD", "--binary"],
        capture_output=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    ).stdout
    if not diff:
        return
    applied = subprocess.run(
        ["git", "-C", str(worktree_dir), "apply", "--whitespace=nowarn"],
        input=diff,
        capture_output=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    if applied.returncode != 0:
        logger.warning(
            "Failed to carry uncommitted changes into worktree: %s",
            applied.stderr.decode(errors="replace").strip(),
        )


REVIEW_PROMPT = """你是代码审查者，只读不写：不要修改、创建或删除任何文件，不要提交。

审查对象是这个仓库里尚未提交的改动（用 `git diff` 查看；需要上下文时直接读文件）。
只报告真实的问题：会导致错误行为的 bug、遗漏的边界情况、与周边代码不一致之处。
不要复述改动内容，不要给风格偏好。

输出格式：每个问题一段，第一行是 `[严重|一般|轻微] 文件:行号 — 一句话问题`，
下面一两句说明触发条件和后果。没有发现问题就只回复「未发现问题」。"""


def _snapshot_worktree(path: Path) -> tuple[str | None, set[str]]:
    """开跑前的工作区快照：(代表当前工作区的提交, 已有的未跟踪文件)。

    就地执行时用户往往已有未提交的改动；不先拍快照，这些改动会被当成子任务
    的产出报回去。``git stash create`` 只生成提交对象，不动工作区和 stash 列表。
    """
    if not is_git_repo(path):
        return None, set()
    try:
        stash = subprocess.run(
            ["git", "-C", str(path), "stash", "create"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        ).stdout.strip()
        head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        ).stdout.strip()
        return stash or head or None, _untracked_files(path)
    except (subprocess.SubprocessError, OSError):
        return None, set()


def _untracked_files(path: Path) -> set[str]:
    out = subprocess.run(
        ["git", "-C", str(path), "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    ).stdout
    return {line for line in out.splitlines() if line}


def _collect_git_changes(
    path: Path,
    base_commit: str | None = None,
    untracked_before: set[str] | None = None,
) -> tuple[list[str], str]:
    """子任务带来的改动：相对开跑前快照的 diff，加上新出现的未跟踪文件。"""
    if not is_git_repo(path):
        return [], ""
    ref = base_commit or "HEAD"
    try:
        changed = subprocess.run(
            ["git", "-C", str(path), "diff", "--name-only", ref],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        ).stdout.splitlines()
        new_untracked = sorted(_untracked_files(path) - (untracked_before or set()))
        diff = subprocess.run(
            ["git", "-C", str(path), "diff", ref],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        ).stdout
        return [f for f in changed if f] + new_untracked, diff
    except Exception as exc:
        logger.warning("Failed to collect git changes: %s", exc)
        return [], ""


def delegate_subtask(
    engine: str,
    instruction: str,
    workspace: Path | str | None = None,
    target_paths: list[str] | None = None,
    timeout: int = _DEFAULT_TIMEOUT_SECONDS,
    isolate: bool = False,
    group: str = "common",
    root_dir: Path | None = None,
    *,
    mode: str = "write",
    log_path: Path | None = None,
    depth: int | None = None,
) -> DelegationResult:
    """Delegates a subtask to another engine.

    Args:
        engine: Target engine (claude, codex, opencode, antigravity, codebuddy).
        instruction: Clear instructions and acceptance criteria for the subtask.
        workspace: Project directory to execute in (default: current working directory).
        target_paths: Optional list of files or folders the subtask focuses on.
        timeout: Maximum execution timeout in seconds.
        isolate: Whether to run in an isolated Git worktree (default: False, in-place).
        group: Resource group to mount (default: "common").
        root_dir: CodeAgent repository root directory.
        mode: ``"write"`` 就地（或在隔离 worktree 里）改代码；``"review"`` 在
            带着当前改动的一次性 worktree 里只读审查，主工作区不会被碰到。
        log_path: 引擎输出实时写到这里（后台委派据此看进度），否则只在内存里收。
        depth: 发起方所在的委派深度，子引擎拿到的是它加一；缺省取当前进程的。

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
    review = mode == "review"
    if review:
        prompt_parts = [REVIEW_PROMPT, ""] + (
            ["审查重点：", *prompt_parts] if instruction.strip() else prompt_parts
        )
    prompt_parts.append(instruction.strip())
    full_prompt = "\n".join(prompt_parts).strip()

    worktree_ctx: AbstractContextManager[dict[str, Any]] = (
        isolated_worktree(ws, "ca/review", carry_changes=True, keep=False)
        if review
        else isolated_worktree(ws)
        if isolate
        else nullcontext(
            {"path": ws, "isolated": False, "branch": None, "repo_root": None}
        )
    )

    t0 = time.time()
    try:
        with worktree_ctx as ctx:
            effective_dir = ctx["path"]
            isolated = ctx["isolated"]
            branch = ctx["branch"]
            if review and not isolated:
                # 非 git 目录或 worktree 建不起来时会退回原地执行，而子引擎是
                # 带 -y 起的——那就谈不上只读，宁可不审。
                return DelegationResult(
                    success=False,
                    engine=canonical_engine,
                    instruction=instruction,
                    exit_code=1,
                    output="",
                    error="review 需要在 git 仓库里建隔离 worktree，当前目录做不到",
                )

            base_commit, untracked_before = _snapshot_worktree(effective_dir)

            env = child_environ()
            env["CA_PROJECT_GROUP"] = group
            env["CA_YOLO"] = "1"
            # 无头的 claude 会把长命令丢到后台、说一句"在等"就退出，任务根本
            # 没做完；被委派出去的引擎必须前台跑完。
            env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] = "1"
            env[DEPTH_ENV] = str((current_depth() if depth is None else depth) + 1)

            cmd = [
                sys.executable,
                str(target_script),
                "-y",
                "--non-interactive",
                full_prompt,
            ]

            proc: subprocess.CompletedProcess[Any]
            if log_path is not None:
                with open(log_path, "w", encoding="utf-8", errors="replace") as log:
                    proc = subprocess.run(
                        cmd,
                        cwd=str(effective_dir),
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=timeout,
                    )
                output = log_path.read_text(encoding="utf-8", errors="replace")
            else:
                proc = subprocess.run(
                    cmd,
                    cwd=str(effective_dir),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                )
                output = (proc.stdout or "") + (
                    "\n" + proc.stderr if proc.stderr else ""
                )

            duration = time.time() - t0
            # review 的 worktree 里本来就带着用户的改动，那不是审查者的产出。
            files_changed, diff = (
                ([], "")
                if review
                else _collect_git_changes(effective_dir, base_commit, untracked_before)
            )

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
                error=None
                if proc.returncode == 0
                else f"Process exited with code {proc.returncode}",
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
