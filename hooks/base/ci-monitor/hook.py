import json
import subprocess
import sys
import time

POLL_INTERVAL = 5
MAX_WAIT_SECS = 30


def _get_branch() -> str:
    r = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True
    )
    return r.stdout.strip()


def _get_latest_run(branch: str) -> dict | None:
    r = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--branch",
            branch,
            "--limit",
            "1",
            "--json",
            "databaseId,status,conclusion,url,name",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    try:
        runs = json.loads(r.stdout)
        return runs[0] if runs else None
    except Exception:
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if "git push" not in command:
        sys.exit(0)

    branch = _get_branch()
    if not branch or branch == "main":
        sys.exit(0)

    print(f"\n⏳ [CI] 等待 CI 启动 (branch: {branch}) ...", flush=True)

    run = None
    for _ in range(MAX_WAIT_SECS // POLL_INTERVAL):
        run = _get_latest_run(branch)
        if run:
            break
        time.sleep(POLL_INTERVAL)

    if not run:
        print("⚠️  [CI] 未检测到 CI 运行，请手动检查", flush=True)
        sys.exit(0)

    print(f"🔗 [CI] {run['name']}  →  {run['url']}", flush=True)

    result = subprocess.run(
        ["gh", "run", "watch", str(run["databaseId"]), "--interval", "10"],
    )

    if result.returncode == 0:
        print("\n✅ [CI] 所有检查通过！", flush=True)
    else:
        print("\n❌ [CI] 检查未通过，请查看上方详情", flush=True)


if __name__ == "__main__":
    main()
