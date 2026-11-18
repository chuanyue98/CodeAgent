import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

_GIT_OPTIONS_WITH_VALUE = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
    "--super-prefix",
    "--config-env",
}
_SHELL_EXECUTABLES = {"sh", "bash", "zsh", "dash", "pwsh", "powershell", "cmd"}
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _deny(reason: str) -> None:
    # 保持 ASCII 转义：Windows 上管道的 stdout 是 cp1252，直接写中文会抛异常，
    # hook 崩掉就等于放行。
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def _split_shell_segments(command: str) -> list[str]:
    """按未加引号的 shell 分隔符切分命令段，避免跨引号误切。"""
    segments: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    i = 0
    n = len(command)

    while i < n:
        ch = command[i]
        if escaped:
            current.append(ch)
            escaped = False
            i += 1
            continue
        if ch == "\\" and not in_single:
            current.append(ch)
            escaped = True
            i += 1
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            current.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            current.append(ch)
            i += 1
            continue
        if not in_single and not in_double:
            if command.startswith(("&&", "||"), i):
                segments.append("".join(current))
                current = []
                i += 2
                continue
            if ch in (";", "|", "&", "\n", "\r"):
                segments.append("".join(current))
                current = []
                i += 1
                continue
        current.append(ch)
        i += 1

    if current:
        segments.append("".join(current))
    return segments


def _tokenize_segment(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def _command_basename(token: str) -> str:
    name = token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _is_git_commit_or_push(command: str, *, _depth: int = 0) -> bool:
    """判断 shell 命令是否尝试执行 git commit 或 git push。"""
    for segment in _split_shell_segments(command):
        tokens = _tokenize_segment(segment)
        idx = 0
        while idx < len(tokens) and _ENV_ASSIGN_RE.match(tokens[idx]):
            idx += 1
        if idx >= len(tokens):
            continue

        cmd_name = _command_basename(tokens[idx])
        if cmd_name == "git":
            sub_idx = idx + 1
            while sub_idx < len(tokens):
                tok = tokens[sub_idx]
                if tok in _GIT_OPTIONS_WITH_VALUE:
                    sub_idx += 2
                    continue
                if tok.startswith("-"):
                    sub_idx += 1
                    continue
                if tok in ("commit", "push"):
                    return True
                break
        elif _depth == 0 and cmd_name in _SHELL_EXECUTABLES:
            for flag_idx in range(idx + 1, len(tokens) - 1):
                if tokens[flag_idx].lower() in ("-c", "/c"):
                    if _is_git_commit_or_push(tokens[flag_idx + 1], _depth=1):
                        return True
                    break
    return False


def get_current_branch(cwd: str | None = None) -> str | None:
    """获取当前分支名；兼容尚未产生任何提交的 unborn 分支。"""
    run_cwd = cwd if cwd and Path(cwd).is_dir() else None
    for git_args in (
        ["git", "symbolic-ref", "--short", "HEAD"],
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
    ):
        try:
            result = subprocess.run(
                git_args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                cwd=run_cwd,
            )
            branch = result.stdout.strip()
            if branch:
                return branch
        except Exception:
            continue
    return None


def main() -> None:
    try:
        # 引擎按 UTF-8 写 stdin；不能用 sys.stdin，它在 Windows 上按 cp1252 解码。
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except Exception:
        sys.exit(0)

    if not isinstance(data, dict):
        sys.exit(0)

    if data.get("tool_name") not in ("run_shell_command", "Bash"):
        sys.exit(0)

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        sys.exit(0)

    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        sys.exit(0)

    if _is_git_commit_or_push(command):
        cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
        current_branch = get_current_branch(cwd=cwd)
        protected_branches = {"main", "master"}

        if current_branch in protected_branches:
            _deny(
                f"禁止直接在 {current_branch} 分支进行 commit 或 push 操作。请创建特性分支并提交 Pull Request。"
            )
            sys.exit(0)


if __name__ == "__main__":
    main()
