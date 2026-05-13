import json
import subprocess
import sys


def _deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
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
        data = json.load(sys.stdin)
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
        if current_branch == "main":
            _deny(
                "禁止直接在 main 分支进行 commit 或 push 操作。请创建特性分支并提交 Pull Request。"
            )
            sys.exit(0)


if __name__ == "__main__":
    main()
