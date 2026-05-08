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


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if "git commit" not in command:
        sys.exit(0)

    check = subprocess.run(
        ["uv", "run", "ruff", "check", "."],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        _deny(f"ruff check 未通过，请修复后再提交：\n{check.stdout.strip()}")
        sys.exit(0)

    fmt = subprocess.run(
        ["uv", "run", "ruff", "format", "--check", "."],
        capture_output=True,
        text=True,
    )
    if fmt.returncode != 0:
        _deny(
            f"ruff format 未通过，请运行 `uv run ruff format .` 格式化后再提交：\n{fmt.stdout.strip()}"
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
