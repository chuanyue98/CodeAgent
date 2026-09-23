"""启动时把 codeagent MCP（跨引擎委派）挂进引擎，只对本次会话生效。

与技能、插件同一原则：不写引擎的用户级配置。各引擎的单会话挂法（实机确认）：

- claude / codebuddy：``--mcp-config=<json>``。必须用 ``=`` 写法——这个参数是
  变长的，空格写法会把后面的首条消息当成配置文件名吞掉。
- codex：``-c mcp_servers.codeagent.<键>=<TOML 值>`` 覆盖配置。
- opencode：``OPENCODE_CONFIG_CONTENT``，与用户自己的配置合并。
- antigravity：没有单会话参数，写进 ca 自己管理的插件包，见
  :mod:`core.engine_base.plugin_bundle_mixin`。

到了委派深度上限（本身就是被委派出来的）时一律不挂，见
:mod:`core.delegation_depth`。
"""

from __future__ import annotations

import json
from typing import Any

from core.delegation_depth import MCP_SERVER_NAME, codeagent_mcp_server

OPENCODE_CONFIG_CONTENT = "OPENCODE_CONFIG_CONTENT"


def _toml(value: Any) -> str:
    """codex ``-c`` 的值按 TOML 解析；字符串与字符串数组用 JSON 写法恰好合法。"""
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k} = {_toml(v)}" for k, v in value.items()) + "}"
    return json.dumps(value, ensure_ascii=False)


class _McpMixin:
    """各引擎挂载 codeagent MCP 的原生写法。"""

    def mcp_config_arg(self) -> list[str]:
        """claude / codebuddy 的 ``--mcp-config=<json>``，不挂时为空。"""
        server = codeagent_mcp_server()
        if server is None:
            return []
        config = {"mcpServers": {MCP_SERVER_NAME: {"type": "stdio", **server}}}
        return ["--mcp-config=" + json.dumps(config, ensure_ascii=False)]

    def codex_mcp_overrides(self) -> list[str]:
        server = codeagent_mcp_server()
        if server is None:
            return []
        prefix = f"mcp_servers.{MCP_SERVER_NAME}"
        return [
            arg
            for key, value in server.items()
            for arg in ("-c", f"{prefix}.{key}={_toml(value)}")
        ]

    def apply_opencode_mcp_env(self, env: dict[str, str]) -> None:
        """把服务并进 ``OPENCODE_CONFIG_CONTENT``，保留调用方已有的内容。"""
        server = codeagent_mcp_server()
        if server is None:
            return
        try:
            content = json.loads(env.get(OPENCODE_CONFIG_CONTENT) or "{}")
        except ValueError:
            content = {}
        if not isinstance(content, dict):
            content = {}
        mcp = content.setdefault("mcp", {})
        if isinstance(mcp, dict):
            mcp[MCP_SERVER_NAME] = {
                "type": "local",
                "command": [server["command"], *server["args"]],
                "environment": server["env"],
            }
        env[OPENCODE_CONFIG_CONTENT] = json.dumps(content, ensure_ascii=False)
