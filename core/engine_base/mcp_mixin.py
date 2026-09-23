"""启动时把 codeagent MCP（跨引擎委派）挂进引擎，只对本次会话生效。

与技能、插件同一原则：不写引擎的用户级配置。各引擎的单会话挂法（实机确认）：

- claude / codebuddy：``--mcp-config=<json>``。必须用 ``=`` 写法——这个参数是
  变长的，空格写法会把后面的首条消息当成配置文件名吞掉。codebuddy 另外用
  ``--agents`` 定义一个等委派结果的后台子代理。
- codex：``-c mcp_servers.codeagent.<键>=<TOML 值>`` 覆盖配置。
- opencode：``OPENCODE_CONFIG_CONTENT``，与用户自己的配置合并；同时打开后台子代理。
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
OPENCODE_BACKGROUND_SUBAGENTS = "OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS"

DELEGATION_AGENT_NAME = "ca-delegate"
DELEGATION_AGENT_DESCRIPTION = (
    "跨引擎委派：用户点名要另一个编码引擎（claude / codex / opencode / "
    "codebuddy / antigravity）做事时（如“让 claude review 一下”），先用 "
    "ToolSearch 找到 codeagent 的 ca_delegate 发起，拿到 run_id 后把 run_id "
    "交给本代理，它在后台等到委派结束，结果自动交回。"
)
DELEGATION_AGENT_PROMPT = """你只负责等一个已经发起的 codeagent 委派，不要自己动手改代码或审查：
1. 用 ToolSearch 找到 codeagent 的 ca_delegate_wait 工具。
2. 用收到的 run_id 反复调用 ca_delegate_wait，直到 status 不再是 running。
3. 把结果里的 status、summary、files_changed、diff、error 原样返回。"""


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

    def delegation_agent_arg(self) -> list[str]:
        """codebuddy 的 ``--agents=<json>``：本次会话专用的后台委派子代理。

        codebuddy 不把 MCP 服务的 instructions 交给模型，MCP 工具又是延迟加载的，
        主会话根本不知道能委派；子代理的描述却会列进它的提示词。``background``
        让子代理总在后台跑，跑完由引擎把结果交回主会话。
        """
        if codeagent_mcp_server() is None:
            return []
        agents = {
            DELEGATION_AGENT_NAME: {
                "description": DELEGATION_AGENT_DESCRIPTION,
                "prompt": DELEGATION_AGENT_PROMPT,
                "background": True,
            }
        }
        return ["--agents=" + json.dumps(agents, ensure_ascii=False)]

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
        # 委派由后台子代理代办、跑完自动回报主会话；opencode 不开这个开关时
        # task 工具的 background=true 直接报错。
        env.setdefault(OPENCODE_BACKGROUND_SUBAGENTS, "true")
