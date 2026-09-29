"""MCP server and tool messages."""

MCP_MESSAGES: dict[str, dict[str, str]] = {
    "mcp.bad_env_pair": {
        "en": "[X] --env expects KEY=VALUE, got: {pair}",
        "zh": "[X] --env 需要 KEY=VALUE 格式，收到: {pair}",
    },
    "mcp.error": {"en": "[X] {error}", "zh": "[X] {error}"},
    "mcp.added": {
        "en": "[OK] Added '{name}' to {engine} ({scope} scope)",
        "zh": "[OK] 已将 '{name}' 添加到 {engine} ({scope}作用域)",
    },
    "mcp.scope_project": {"en": "project", "zh": "项目级"},
    "mcp.scope_global": {"en": "global", "zh": "全局"},
    "mcp.sync_hint": {
        "en": "   Copy it to the others with: ca mcp sync {engine}",
        "zh": "   同步到其他引擎: ca mcp sync {engine}",
    },
    "mcp.sync_targets": {
        "en": "   (targets: {targets})",
        "zh": "   (目标引擎: {targets})",
    },
    "mcp.not_found": {
        "en": "[X] No such MCP server in {engine}: {name}",
        "zh": "[X] {engine} 中没有这个 MCP 服务: {name}",
    },
    "mcp.removed": {
        "en": "[OK] Removed '{name}' from {engine}",
        "zh": "[OK] 已从 {engine} 移除 '{name}'",
    },
    "mcp.nothing_to_sync": {
        "en": "Nothing to sync — {source} has no MCP servers configured.",
        "zh": "无需同步 —— {source} 没有配置任何 MCP 服务。",
    },
    "mcp.dry_run": {
        "en": "Dry run — nothing was written.",
        "zh": "演练模式 —— 未写入任何内容。",
    },
    "mcp.partial_failure": {
        "en": "\n[!] {failed} of {total} operations failed.",
        "zh": "\n[!] {total} 项操作中有 {failed} 项失败。",
    },
}
