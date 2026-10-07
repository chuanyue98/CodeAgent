import json
import subprocess
import sys


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


def get_current_branch():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def main():
    try:
        # 引擎按 UTF-8 写 stdin；不能用 sys.stdin，它在 Windows 上按 cp1252 解码。
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "run_shell_command":
        # compatibility check for other potential tool names in different environments
        if data.get("tool_name") != "Bash":
            sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")

    # Check for git commit or push commands
    if "git commit" in command or "git push" in command:
        current_branch = get_current_branch()
        protected_branches = ["main", "master"]

        if current_branch in protected_branches:
            _deny(
                f"禁止直接在 {current_branch} 分支进行 commit 或 push 操作。请创建特性分支并提交 Pull Request。"
            )
            sys.exit(0)


if __name__ == "__main__":
    main()
