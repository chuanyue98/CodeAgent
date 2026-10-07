"""随仓库发布的 branch-protection hook 本身：在 Windows 的默认编码下也得拦得住。

Windows 上管道的 stdin/stdout 默认是 cp1252。hook 读中文命令或输出中文理由时
一旦抛异常就会以非 0 退出、什么也不输出，引擎只当它没意见，提交就放过去了。
这里用 ``PYTHONIOENCODING=cp1252`` 在任何平台上复现那个环境。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "hooks/base/branch-protection/hook.py"


@pytest.fixture
def repo_on_main(tmp_path) -> Path:
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=tmp_path, check=True)
    subprocess.run([*git, "commit", "-qm", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _run_hook(cwd: Path, command: str, encoding: str) -> subprocess.CompletedProcess:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        cwd=cwd,
        env={**os.environ, "PYTHONIOENCODING": encoding},
        timeout=30,
    )


@pytest.mark.parametrize("encoding", ["utf-8", "cp1252"])
@pytest.mark.parametrize("command", ["git commit -m x", 'git commit -m "修复登录"'])
def test_a_commit_on_main_is_denied_whatever_the_console_encoding(
    repo_on_main, encoding, command
):
    result = _run_hook(repo_on_main, command, encoding)

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    decision = json.loads(result.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "main" in decision["permissionDecisionReason"]


def test_non_git_commands_pass_silently(repo_on_main):
    result = _run_hook(repo_on_main, "ls", "cp1252")

    assert result.returncode == 0
    assert result.stdout == b""
