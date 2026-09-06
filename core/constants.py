"""Shared constants used across CodeAgent's backend.

Single source of truth for values that were previously hand-duplicated
across many modules (see the 2026-07-28 engineering inspection) --
duplication meant adding or retiring an engine required remembering to
update every copy, with nothing catching a missed one.
"""

from __future__ import annotations

# The engine CLIs CodeAgent knows how to launch/manage. Used for
# request validation (reject an unknown `engine` field) and for iterating
# "every engine" (e.g. building the /api/engines list).
#
# freebuff 的免费版 CLI 目前只有交互 TUI（login / --continue / --cwd），没有
# headless / ACP 通道，因此带注入的交互启动、历史浏览与恢复可用，而一切需要
# "无人值守跑一次"的入口（后台任务、Chat 单轮、batch-run、NL-cron、MCP 管理）
# 都必须从下方两个分组取引擎，不能落到 freebuff 上。
ENGINES = frozenset({"claude", "opencode", "codex", "codebuddy", "freebuff"})

#: Engines that expose a headless / structured-output channel (print mode,
#: ``exec --json``, ACP ...). 这是后台任务、Chat 单轮等无人值守入口的候选集。
HEADLESS_ENGINES = frozenset({"claude", "opencode", "codex", "codebuddy"})

#: Engines with a native MCP server config surface (``ca mcp`` 与 doctor 的
#: 漂移检查只在它们之间比较)。freebuff 没有 MCP 配置，列出/同步它只会制造噪音。
MCP_ENGINES = frozenset({"claude", "opencode", "codex", "codebuddy"})

# Directory under the system temp dir where engines drop the assembled
# prompt for a run. Shared so `ca doctor` probes the location engines
# really use -- it previously checked a project-root path that
# `write_temp_prompt` had long since stopped writing to.
TEMP_PROMPT_DIRNAME = "codeagent-prompts"
