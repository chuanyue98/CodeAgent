"""跨引擎委派的深度，以及据此决定要不要给引擎挂 codeagent MCP。

委派出去的子引擎由 worker 带着 ``CA_DELEGATION_DEPTH=<父深度+1>`` 拉起。深度
到了上限，启动器就不挂 codeagent MCP，子引擎连委派工具都看不到——做法同
claude-codex-bridge 的 ``BRIDGE_DEPTH``（到限隐藏工具而非报错）和 Codex
``agents.max_depth`` 的默认值 1：子代理不再往下派。
"""

from __future__ import annotations

import os
import sys
from typing import Any

from core.resource_locator import CODE_ROOT

DEPTH_ENV = "CA_DELEGATION_DEPTH"

#: 主会话是 0 层；委派出去的子引擎是 1 层，已到上限。
MAX_DELEGATION_DEPTH = 1

#: 挂进各引擎时用的服务名，引擎里的工具名会带上它（``mcp__codeagent__…``）。
MCP_SERVER_NAME = "codeagent"


def current_depth(env: dict[str, str] | None = None) -> int:
    raw = (env if env is not None else os.environ).get(DEPTH_ENV, "")
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def may_delegate(env: dict[str, str] | None = None) -> bool:
    return current_depth(env) < MAX_DELEGATION_DEPTH


def codeagent_mcp_server() -> dict[str, Any] | None:
    """本次会话要挂的 codeagent MCP 服务（stdio），到了深度上限返回 None。

    用当前解释器加 ``PYTHONPATH`` 拉起，源码检出与安装包两种形态都能 import
    到 ``core``；不经 ``uv run``，省掉每次起服务的解析开销。
    """
    if not may_delegate():
        return None
    return {
        "command": sys.executable,
        "args": ["-m", "core.services.mcp_server_service", "--delegation"],
        "env": {"PYTHONPATH": str(CODE_ROOT), DEPTH_ENV: str(current_depth())},
    }
