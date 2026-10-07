"""Doctor diagnostics and health check messages."""

DOCTOR_MESSAGES: dict[str, dict[str, str]] = {
    "doctor.title": {"en": "CodeAgent Health Check", "zh": "CodeAgent 健康检查"},
    "doctor.mode_dry_run": {
        "en": "--dry-run mode: previewing what --fix would change; nothing is applied",
        "zh": "--dry-run 模式: 仅预览 --fix 会做的改动，不会实际执行",
    },
    "doctor.mode_fix": {
        "en": "--fix mode: auto-repairable issues will be resolved",
        "zh": "--fix 模式: 将自动修复可修复的问题",
    },
    "doctor.section_runtime": {"en": "Runtime", "zh": "运行环境"},
    "doctor.section_configuration": {"en": "Configuration", "zh": "配置"},
    "doctor.section_context": {"en": "Context Resolution", "zh": "上下文解析"},
    "doctor.section_environment": {"en": "Environment", "zh": "环境"},
    "doctor.section_parity": {"en": "Cross-Engine Parity", "zh": "跨引擎一致性"},
    "doctor.section_sessions": {"en": "Session Integrity", "zh": "会话完整性"},
    "doctor.result_failures": {
        "en": "  Result: {failures} failure(s), {warnings} warning(s) — run "
        "'ca doctor --fix' for auto-repairs",
        "zh": "  结果: {failures} 项失败，{warnings} 项警告 —— 运行 'ca doctor --fix' "
        "可自动修复",
    },
    "doctor.result_warnings": {
        "en": "  Result: {warnings} warning(s) — check the hints above",
        "zh": "  结果: {warnings} 项警告 —— 请查看上方提示",
    },
    "doctor.result_ok": {
        "en": "  Result: all checks passed",
        "zh": "  结果: 全部检查通过",
    },
    "doctor.python_too_old": {
        "en": "CodeAgent requires Python 3.13+",
        "zh": "CodeAgent 需要 Python 3.13+",
    },
    "doctor.python_upgrade": {"en": "Upgrade Python", "zh": "请升级 Python"},
    "doctor.python_unsupported": {
        "en": "Unsupported Python version",
        "zh": "不支持的 Python 版本",
    },
    "doctor.python_upgrade_to": {
        "en": "Upgrade to Python 3.13+",
        "zh": "请升级到 Python 3.13+",
    },
    "doctor.engine_label": {"en": "Engine: {engine}", "zh": "引擎: {engine}"},
    "doctor.engine_missing": {
        "en": "binary not found in PATH",
        "zh": "PATH 中找不到可执行文件",
    },
    "doctor.config_not_found": {"en": "file not found", "zh": "文件不存在"},
    "doctor.config_run_fix": {
        "en": "Run: ca doctor --fix  (seeds config.json from config.example.json)",
        "zh": "运行: ca doctor --fix  (从 config.example.json 生成 config.json)",
    },
    "doctor.config_seeded": {
        "en": "  Created {path} from the bundled template",
        "zh": "  已根据内置模板创建 {path}",
    },
    "doctor.config_unparsable": {
        "en": "failed to load or parse configuration",
        "zh": "配置加载或解析失败",
    },
    "doctor.config_valid": {"en": "valid configuration", "zh": "配置有效"},
    "doctor.dir_subdirs": {"en": "{count} subdirectories", "zh": "{count} 个子目录"},
    "doctor.dir_missing": {"en": "directory not found", "zh": "目录不存在"},
    "doctor.active_group": {
        "en": "Active project group: {group}",
        "zh": "当前项目资源组: {group}",
    },
    "doctor.skill_scanner": {"en": "Skill Scanner", "zh": "技能扫描器"},
    "doctor.hook_scanner": {"en": "Hook Scanner", "zh": "钩子扫描器"},
    "doctor.plugin_scanner": {"en": "Plugin Scanner", "zh": "插件扫描器"},
    "doctor.skills_declared": {
        "en": "Skills ({total} declared)",
        "zh": "技能 (声明 {total} 个)",
    },
    "doctor.skills_missing": {
        "en": "Skills ({total} declared, {missing} missing)",
        "zh": "技能 (声明 {total} 个，缺失 {missing} 个)",
    },
    "doctor.all_resolved": {"en": "all resolved", "zh": "全部解析成功"},
    "doctor.skills_none_detail": {
        "en": "no skills will be mounted for group '{group}'",
        "zh": "资源组 '{group}' 不会挂载任何技能",
    },
    "doctor.skills_none_hint": {
        "en": "Add entries to groups.{group}.skills in config.json (see "
        "config.example.json), or use the Web UI's Config Hub",
        "zh": "请在 config.json 的 groups.{group}.skills 中添加技能 (可参考 "
        "config.example.json)，或通过 Web UI 的 Config Hub 配置",
    },
    "doctor.skills_hint": {
        "en": "Check skills/ directory or config.json groups",
        "zh": "请检查 skills/ 目录或 config.json 中的 groups",
    },
    "doctor.skills_error": {"en": "Skills resolution", "zh": "技能解析"},
    "doctor.hooks_resolved": {
        "en": "Hooks ({count} resolved)",
        "zh": "钩子 (解析 {count} 个)",
    },
    "doctor.hooks_unresolved": {
        "en": "Hooks ({declared} declared, {missing} unresolved)",
        "zh": "钩子 (声明 {declared} 个，未解析 {missing} 个)",
    },
    "doctor.hooks_hint": {
        "en": "Check hooks/ directory or metadata.json files",
        "zh": "请检查 hooks/ 目录或各 metadata.json 文件",
    },
    "doctor.hooks_error": {"en": "Hooks resolution", "zh": "钩子解析"},
    "doctor.plugins_resolved": {
        "en": "Plugins ({count} resolved)",
        "zh": "插件 (解析 {count} 个)",
    },
    "doctor.plugins_unresolved": {
        "en": "Plugins ({declared} declared, {missing} unresolved)",
        "zh": "插件 (声明 {declared} 个，未解析 {missing} 个)",
    },
    "doctor.plugins_hint": {
        "en": "Check plugins/ directory",
        "zh": "请检查 plugins/ 目录",
    },
    "doctor.plugins_error": {"en": "Plugins resolution", "zh": "插件解析"},
    "doctor.skipped": {"en": "Skipped", "zh": "已跳过"},
    "doctor.skipped_no_config": {
        "en": "config.json could not be loaded",
        "zh": "config.json 无法加载",
    },
    "doctor.could_not_evaluate": {
        "en": "could not evaluate: {error}",
        "zh": "无法检测: {error}",
    },
    "doctor.temp_prompt_ok": {
        "en": "Temp prompt dir writable",
        "zh": "临时提示词目录可写",
    },
    "doctor.temp_prompt_label": {"en": "Temp prompt dir", "zh": "临时提示词目录"},
    "doctor.temp_prompt_failed": {
        "en": "not writable: {error}",
        "zh": "不可写: {error}",
    },
    "doctor.temp_prompt_hint": {
        "en": "Check permissions on {path}, or set TMPDIR/TEMP elsewhere",
        "zh": "请检查 {path} 的权限，或将 TMPDIR/TEMP 指向其他位置",
    },
    "doctor.proxy_label": {"en": "Proxy", "zh": "代理"},
    "doctor.proxy_unset": {
        "en": "not configured (use --proxy flag to enable)",
        "zh": "未配置 (使用 --proxy 参数启用)",
    },
    "doctor.proxy_reachable": {"en": "reachable", "zh": "可连通"},
    "doctor.proxy_unreachable": {
        "en": "none of the configured addresses reachable ({addresses})",
        "zh": "配置的地址均无法连通 ({addresses})",
    },
    "doctor.proxy_idle": {
        "en": "configured but not in use this run ({addresses}); `ca --proxy` turns "
        "it on",
        "zh": "已配置但本次未启用 ({addresses})；用 ca --proxy 启用",
    },
    "doctor.proxy_hint": {
        "en": "Start your proxy or update config.json",
        "zh": "请启动代理，或更新 config.json",
    },
    "doctor.symlink_label": {"en": "Symlink capability", "zh": "符号链接能力"},
    "doctor.symlink_unix": {
        "en": "Unix (symlinks available)",
        "zh": "Unix (支持符号链接)",
    },
    "doctor.junction_label": {
        "en": "Windows junction support",
        "zh": "Windows 目录联接支持",
    },
    "doctor.junction_ok": {
        "en": "available (no admin required)",
        "zh": "可用 (无需管理员权限)",
    },
    "doctor.junction_failed": {
        "en": "mklink /j failed — skill linking may not work ({detail})",
        "zh": "mklink /j 失败 —— 技能挂载可能无法工作 ({detail})",
    },
    "doctor.junction_exit_code": {
        "en": "mklink /j exited with code {code}",
        "zh": "mklink /j 退出码为 {code}",
    },
    "doctor.junction_hint": {
        "en": "Enable Developer Mode or run as Administrator",
        "zh": "请开启开发者模式，或以管理员身份运行",
    },
    "doctor.hook_delivery_label": {"en": "Hook delivery", "zh": "钩子生效情况"},
    "doctor.hook_delivery_none": {
        "en": "no hooks configured for this group",
        "zh": "当前资源组没有配置钩子",
    },
    "doctor.hook_delivery_count": {
        "en": "Hook delivery ({count})",
        "zh": "钩子生效情况 ({count})",
    },
    "doctor.hook_delivery_supported": {
        "en": "claude, opencode, codebuddy: supported",
        "zh": "claude, opencode, codebuddy: 支持",
    },
    "doctor.codex_hooks_label": {"en": "codex hooks", "zh": "codex 钩子"},
    "doctor.codex_trusted": {"en": "project is trusted", "zh": "项目已被信任"},
    "doctor.codex_untrusted": {
        "en": "'{project}' is not a trusted codex project; hooks are ignored",
        "zh": "'{project}' 不是受信任的 codex 项目，钩子会被忽略",
    },
    "doctor.codex_trust_hint": {
        "en": 'Add [projects."{project}"] with trust_level = "trusted" to {config}',
        "zh": '在 {config} 中加入 [projects."{project}"] 并设置 trust_level = '
        '"trusted"',
    },
    "doctor.codex_trust_unknown": {
        "en": "trust state unknown: {error}",
        "zh": "信任状态未知: {error}",
    },
    "doctor.mcp_drift_label": {"en": "MCP drift", "zh": "MCP 配置漂移"},
    "doctor.mcp_servers_label": {"en": "MCP servers", "zh": "MCP 服务"},
    "doctor.mcp_none": {
        "en": "none configured on any engine",
        "zh": "所有引擎均未配置",
    },
    "doctor.mcp_in_sync_label": {
        "en": "MCP servers ({count})",
        "zh": "MCP 服务 ({count} 个)",
    },
    "doctor.mcp_in_sync": {
        "en": "configured identically on all four engines",
        "zh": "四个引擎的配置完全一致",
    },
    "doctor.mcp_drift_count": {
        "en": "MCP drift ({count} server(s) not on every engine)",
        "zh": "MCP 配置漂移 ({count} 个服务未覆盖全部引擎)",
    },
    "doctor.mcp_drift_entry": {
        "en": "{name} (on: {engines})",
        "zh": "{name} (已配置: {engines})",
    },
    "doctor.mcp_drift_more": {"en": ", +{count} more", "zh": ", 另有 {count} 个"},
    "doctor.mcp_drift_hint": {
        "en": "Run: ca mcp sync <engine>   (add --dry-run to preview)",
        "zh": "运行: ca mcp sync <engine>   (加 --dry-run 可预览)",
    },
    "doctor.stale_label": {"en": "Stale injections", "zh": "残留注入"},
    "doctor.stale_found": {
        "en": "left in the workspace by a session that did not exit cleanly: {names}",
        "zh": "未正常退出的会话留在工作区里的注入: {names}",
    },
    "doctor.stale_hint": {
        "en": "Run: ca doctor --fix  (restores .bak backups, removes only what ca created)",
        "zh": "运行: ca doctor --fix  (从 .bak 备份恢复，只删除 ca 自己生成的内容)",
    },
    "doctor.stale_none": {"en": "none found", "zh": "未发现"},
    "doctor.dry_run_banner": {
        "en": "  --dry-run: no changes will be made. Preview of 'ca doctor --fix':",
        "zh": "  --dry-run: 不会做任何改动。以下是 'ca doctor --fix' 的预览:",
    },
    "doctor.applying_fixes": {"en": "  Applying fixes...", "zh": "  正在修复..."},
    "doctor.fixes_done": {
        "en": "  Done. Re-run 'ca doctor' to verify.",
        "zh": "  完成。请重新运行 'ca doctor' 确认。",
    },
    "doctor.restored": {
        "en": "  Restored {path} from backup",
        "zh": "  已从备份恢复 {path}",
    },
    "doctor.removed_injected": {
        "en": "  Removed injected {path}",
        "zh": "  已删除注入的 {path}",
    },
    "doctor.would_restore": {
        "en": "  Would restore {path} from backup",
        "zh": "  将从备份恢复 {path}",
    },
    "doctor.would_remove": {
        "en": "  Would remove injected {path}",
        "zh": "  将删除注入的 {path}",
    },
}
