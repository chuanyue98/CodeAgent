#!/usr/bin/env python3
"""自动启动 OpenCode 并执行任务 (统一架构版)"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 确保能找到 core 模块
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.cli_utils import require_engine_cli
from core.engine_base import BaseEngine, register_signal_handler
from core.logging_config import get_logger
from core.task_lib import (
    TASK_FILE_SUFFIX,
    handle_task_mode,
    show_tasks,
)

logger = get_logger(__name__)


class OpenCodeEngine(BaseEngine):
    """OpenCode 引擎的具体实现"""

    OPENCODE_COMMAND = "opencode"

    def __init__(self):
        super().__init__("OpenCode", "opencode-default")

    def _get_plugin_link_dir(self):
        return (Path.cwd() / ".opencode" / "plugins").absolute()

    def ensure_plugins_link(self):
        """为 OpenCode 优化插件挂载逻辑：支持扁平化链接并自动生成通用适配器"""
        plugins_to_mount = self.get_plugins_to_mount()
        if not plugins_to_mount:
            self.cleanup_plugins_link()
            return

        link_dir = self._get_plugin_link_dir()
        link_dir.mkdir(parents=True, exist_ok=True)

        desired_native_names: set[str] = set()
        for plugin_meta in plugins_to_mount:
            plugin_src_str = plugin_meta.get("_plugin_dir")
            if not plugin_src_str:
                continue
            native_dir = Path(plugin_src_str).resolve() / ".opencode" / "plugins"
            if native_dir.is_dir():
                desired_native_names.update(item.name for item in native_dir.iterdir())
        self._remove_stale_managed_links(link_dir, desired_native_names)

        # Generated adapters are recreated from the current plugin selection.
        for item in link_dir.glob("ca_adapter_*.js"):
            try:
                if "_ca_injected: true" in item.read_text(encoding="utf-8")[:500]:
                    item.unlink()
            except OSError:
                pass

        mounted_count = 0
        for plugin_meta in plugins_to_mount:
            plugin_name = plugin_meta["name"]
            plugin_src_str = plugin_meta.get("_plugin_dir")
            if not plugin_src_str:
                continue

            plugin_src = Path(plugin_src_str).resolve()

            # 1. 优先检查是否有原生适配器
            opencode_inner_plugins = plugin_src / ".opencode" / "plugins"
            if opencode_inner_plugins.is_dir():
                # 链接内部所有的内容（根据 Review 建议：链接所有文件和文件夹而不仅仅是 JS）
                for item in opencode_inner_plugins.iterdir():
                    target_link = link_dir / item.name
                    if self._ensure_managed_link(item, target_link, link_dir):
                        mounted_count += 1
                continue

            # 2. 如果没有原生适配器，自动生成一个通用适配器
            adapter_content = self._generate_universal_adapter(plugin_name, plugin_src)
            adapter_file = link_dir / f"ca_adapter_{plugin_name.replace('/', '_')}.js"

            if adapter_file.exists():
                try:
                    existing = adapter_file.read_text(encoding="utf-8")
                except OSError:
                    existing = ""
                if "_ca_injected: true" not in existing[:500]:
                    logger.warning(
                        "Refusing to replace unmanaged path: %s", adapter_file
                    )
                    continue

            # 写入生成的适配器代码 (带有 _ca_injected 标记以便清理)
            with open(adapter_file, "w", encoding="utf-8") as f:
                f.write(adapter_content)
            mounted_count += 1

        if mounted_count:
            logger.info(
                "Ensured %d plugins (with auto-adapters) in %s", mounted_count, link_dir
            )

    def _generate_universal_adapter(self, name: str, src_path: Path) -> str:
        """生成符合 OpenCode 规范的通用 JS 适配器代码"""
        skill_md_path = src_path / "SKILL.md"
        scripts_dir = src_path / "scripts"

        # 路径处理 (Windows 兼容)
        abs_skill = str(skill_md_path.absolute()).replace("\\", "/")

        # 探测脚本
        tool_defs = []
        if scripts_dir.is_dir():
            for script in scripts_dir.iterdir():
                if script.is_file() and script.suffix in (".py", ".sh", ".ps1"):
                    safe_script_name = f"{name}_{script.stem}".replace(
                        "/", "_"
                    ).replace("-", "_")
                    tool_defs.append(
                        {
                            "name": safe_script_name,
                            "path": str(script.absolute()).replace("\\", "/"),
                            "ext": script.suffix,
                        }
                    )

        # 使用 json.dumps 安全转义所有嵌入 JS 的字符串，防止路径/名称注入
        name_js = json.dumps(name)
        name_safe = name.replace("*/", "*_/").replace("/*", "/_*")
        skill_path_js = json.dumps(abs_skill)

        # 构建工具定义块
        tool_lines: list[str] = []
        for tool in tool_defs:
            cmd = "python" if tool["ext"] == ".py" else "sh"
            if tool["ext"] == ".ps1":
                cmd = "powershell"
            tool_name_js = json.dumps(tool["name"])
            tool_desc_js = json.dumps(
                f"Execute script from plugin {name}: {Path(tool['path']).name}"
            )
            tool_cmd_js = json.dumps(f"{cmd} {tool['path']} ")
            tool_lines.append(
                "      {\n"
                f"        name: {tool_name_js},\n"
                f"        description: {tool_desc_js},\n"
                "        execute: async (args) => {\n"
                "          const scriptArgs = typeof args === 'string' ? args : JSON.stringify(args);\n"
                f"          return await client.runShellCommand({tool_cmd_js} + scriptArgs);\n"
                "        }\n"
                "      },"
            )

        tools_block = "\n".join(tool_lines)

        # 生成 JS 模板 — 所有用户可控值通过 json.dumps 转义后嵌入
        js_code = f"""
/**
 * Generated by CodeAgent Universal Adapter
 * Plugin: {name_safe}
 * _ca_injected: true
 */
import fs from 'fs';

export default async ({{ client }}) => {{
  const skillPath = {skill_path_js};
  const pluginName = {name_js};
  let bootstrap = "";

  if (fs.existsSync(skillPath)) {{
    const raw = fs.readFileSync(skillPath, 'utf8');
    const content = raw.replace(/^---[\\s\\S]*?---\\n/, '');
    bootstrap = '\\n<PLUGIN_CONTEXT name="' + pluginName + '">\\n' + content + '\\n</PLUGIN_CONTEXT>\\n';
  }}

  return {{
    'experimental.chat.messages.transform': async (_input, output) => {{
      if (!bootstrap || !output.messages.length) return;
      const firstUser = output.messages.find(m => m.info.role === 'user');
      if (!firstUser || !firstUser.parts.length) return;
      if (firstUser.parts.some(p => p.text && p.text.includes('<PLUGIN_CONTEXT name="' + pluginName + '">'))) return;

      firstUser.parts.unshift({{ type: 'text', text: bootstrap }});
    }},

    tools: [
{tools_block}
    ]
  }};
}};
"""
        return js_code

    # OpenCode 的工具 id 与 Claude 的工具名不同（bash vs Bash）。现有钩子按
    # Claude 的名字匹配（见 hooks/base/*），所以桥接层做一次归一化，让同一份
    # 钩子在四个引擎下都能命中；未知 id 原样透传，不臆造映射。
    TOOL_NAME_MAP = {
        "bash": "Bash",
        "edit": "Edit",
        "read": "Read",
        "write": "Write",
        "glob": "Glob",
        "grep": "Grep",
        "patch": "Patch",
        "webfetch": "WebFetch",
        "todowrite": "TodoWrite",
        "todoread": "TodoRead",
        "task": "Task",
    }

    HOOK_TIMEOUT_MS = 600_000

    def _get_hook_bridge_path(self) -> Path:
        return self._get_plugin_link_dir() / "ca_hooks_bridge.js"

    def ensure_hooks_bridge(self, hooks: list[dict]) -> bool:
        """Generates a JS plugin that runs CodeAgent's shell hooks under OpenCode.

        OpenCode has no shell-command hook mechanism — its hooks are JS
        functions exported by a plugin module — so the canonical
        ``before_tool``/``after_tool`` commands are bridged through a generated
        plugin rather than injected into a settings file.

        Returns:
            bool: True if a bridge was written.
        """
        bridge_path = self._get_hook_bridge_path()

        if not hooks:
            self._remove_generated_file(bridge_path)
            return False

        before = [h for h in hooks if h.get("event") == "before_tool"]
        after = [h for h in hooks if h.get("event") == "after_tool"]
        if not before and not after:
            self._remove_generated_file(bridge_path)
            return False

        if bridge_path.exists():
            try:
                existing = bridge_path.read_text(encoding="utf-8")[:500]
            except OSError:
                existing = ""
            if "_ca_injected: true" not in existing:
                logger.warning("Refusing to replace unmanaged path: %s", bridge_path)
                return False

        bridge_path.parent.mkdir(parents=True, exist_ok=True)
        bridge_path.write_text(
            self._generate_hook_bridge(before, after), encoding="utf-8"
        )
        logger.info(
            "Bridged %d before_tool / %d after_tool hook(s) into %s",
            len(before),
            len(after),
            bridge_path,
        )
        return True

    def _remove_generated_file(self, path: Path) -> None:
        """Deletes a generated file, but only if CodeAgent generated it."""
        if not path.exists():
            return
        try:
            if "_ca_injected: true" in path.read_text(encoding="utf-8")[:500]:
                path.unlink()
        except OSError:
            pass

    def _generate_hook_bridge(self, before: list[dict], after: list[dict]) -> str:
        """Builds the bridge plugin's JS source.

        Every embedded value goes through ``json.dumps`` so hook names, commands
        and paths cannot break out of the literal they sit in.
        """

        def spec(hook: dict) -> dict:
            return {"name": hook.get("name") or "hook", "command": hook["command"]}

        before_js = json.dumps([spec(h) for h in before], ensure_ascii=False, indent=2)
        after_js = json.dumps([spec(h) for h in after], ensure_ascii=False, indent=2)
        tool_map_js = json.dumps(self.TOOL_NAME_MAP, ensure_ascii=False, indent=2)

        return f"""\
/**
 * Generated by CodeAgent — shell hook bridge for OpenCode
 * _ca_injected: true
 *
 * OpenCode's hooks are JS functions, not shell commands, so each CodeAgent
 * hook is spawned here with a Claude-shaped JSON payload on stdin. A hook
 * denies a call the same way it does under Claude/codex: by printing
 * {{"hookSpecificOutput": {{"permissionDecision": "deny", ...}}}} or by exiting
 * with code 2. Since OpenCode's tool.execute.before returns void, the only way
 * to stop the call is to throw — so a denial surfaces to the model as a tool
 * error carrying the hook's reason.
 */
import {{ spawn }} from 'child_process';

const BEFORE_HOOKS = {before_js};
const AFTER_HOOKS = {after_js};
const TOOL_NAME_MAP = {tool_map_js};
const TIMEOUT_MS = {self.HOOK_TIMEOUT_MS};

function runHook(command, payload) {{
  return new Promise((resolve) => {{
    let child;
    try {{
      child = spawn(command, {{ shell: true }});
    }} catch (err) {{
      resolve({{ code: 0, stdout: '', stderr: String(err), spawnFailed: true }});
      return;
    }}

    let stdout = '';
    let stderr = '';
    let settled = false;

    const finish = (result) => {{
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    }};

    const timer = setTimeout(() => {{
      try {{ child.kill(); }} catch {{}}
      finish({{ code: 0, stdout, stderr, timedOut: true }});
    }}, TIMEOUT_MS);

    child.stdout.on('data', (d) => {{ stdout += d; }});
    child.stderr.on('data', (d) => {{ stderr += d; }});
    // A hook that never reads stdin makes the write fail with EPIPE; that is
    // not an error condition, so swallow it rather than crash the session.
    child.stdin.on('error', () => {{}});
    child.on('error', (err) => finish({{
      code: 0, stdout, stderr: String(err), spawnFailed: true,
    }}));
    child.on('close', (code) => finish({{ code, stdout, stderr }}));

    try {{
      child.stdin.end(JSON.stringify(payload));
    }} catch {{}}
  }});
}}

function denialReason(result) {{
  // Exit code 2 is Claude's "block, feedback is on stderr" convention.
  if (result.code === 2) return result.stderr.trim() || 'hook exited with code 2';

  const text = (result.stdout || '').trim();
  if (!text.startsWith('{{')) return null;
  let parsed;
  try {{
    parsed = JSON.parse(text);
  }} catch {{
    return null;  // hooks are free to print plain progress text
  }}
  const specific = parsed && parsed.hookSpecificOutput;
  if (specific && specific.permissionDecision === 'deny') {{
    return specific.permissionDecisionReason || 'blocked by hook';
  }}
  return null;
}}

function report(hook, result) {{
  if (result.spawnFailed) {{
    console.error(`[CodeAgent] hook ${{hook.name}} failed to start: ${{result.stderr}}`);
  }} else if (result.timedOut) {{
    console.error(`[CodeAgent] hook ${{hook.name}} timed out after ${{TIMEOUT_MS}}ms`);
  }} else if (result.stderr.trim()) {{
    console.error(`[CodeAgent] ${{hook.name}}: ${{result.stderr.trim()}}`);
  }}
}}

export default async () => {{
  return {{
    'tool.execute.before': async (input, output) => {{
      if (!BEFORE_HOOKS.length) return;
      const payload = {{
        hook_event_name: 'PreToolUse',
        tool_name: TOOL_NAME_MAP[input.tool] || input.tool,
        opencode_tool_name: input.tool,
        tool_input: output.args,
        session_id: input.sessionID,
        cwd: process.cwd(),
      }};
      for (const hook of BEFORE_HOOKS) {{
        const result = await runHook(hook.command, payload);
        report(hook, result);
        const reason = denialReason(result);
        if (reason) {{
          throw new Error(`Blocked by CodeAgent hook '${{hook.name}}': ${{reason}}`);
        }}
      }}
    }},

    'tool.execute.after': async (input, output) => {{
      if (!AFTER_HOOKS.length) return;
      const payload = {{
        hook_event_name: 'PostToolUse',
        tool_name: TOOL_NAME_MAP[input.tool] || input.tool,
        opencode_tool_name: input.tool,
        tool_input: input.args,
        tool_response: output.output,
        session_id: input.sessionID,
        cwd: process.cwd(),
      }};
      for (const hook of AFTER_HOOKS) {{
        const result = await runHook(hook.command, payload);
        report(hook, result);
        // The tool already ran, so throwing here would discard a valid result.
        // Surface the feedback to the model by appending it to the output.
        const reason = denialReason(result);
        if (reason) {{
          output.output = `${{output.output}}\\n\\n[CodeAgent hook '${{hook.name}}'] ${{reason}}`;
        }}
      }}
    }},
  }};
}};
"""

    def cleanup_plugins_link(self):
        """清理所有创建的链接和生成的临时适配器"""
        link_dir = self._get_plugin_link_dir()
        if not link_dir.exists():
            return

        self._cleanup_link_dir(link_dir)

        if not link_dir.exists():
            return
        for item in link_dir.iterdir():
            # 仅删除带有明确 CodeAgent 标记的生成适配器/桥接插件。
            if item.is_file() and item.name.startswith(("ca_adapter_", "ca_hooks_")):
                try:
                    # Windows 不允许删除仍有打开句柄的文件，所以必须先读完关闭
                    # 再 unlink——放在 with 块里会静默失败，生成的适配器就永远
                    # 留在用户项目里了。
                    with open(item, encoding="utf-8") as f:
                        head = f.read(500)
                    if "_ca_injected: true" in head:
                        item.unlink()
                except Exception:
                    pass

        # 如果目录空了则删除
        if link_dir.exists() and not any(link_dir.iterdir()):
            try:
                link_dir.rmdir()
            except Exception:
                pass

    def build_command(self, message: str, non_interactive: bool) -> list[str]:
        if non_interactive:
            # 非交互模式使用 run
            return [self.OPENCODE_COMMAND, "run", message]

        # 交互模式：在当前目录启动 TUI 并注入初始提示词
        return [self.OPENCODE_COMMAND, ".", "--prompt", message]

    def build_chat_command(
        self, message: str, session_id: str | None = None
    ) -> list[str]:
        """Builds a headless JSON command for one ChatPage turn.

        Verified live (see docs/chatpage-cli-spike-results.md spike):
        ``-s/--session <id>`` resumes with full prior context. Legacy Web Chat
        intentionally keeps OpenCode's default permission policy.
        """
        cmd = [self.OPENCODE_COMMAND, "run", message, "--format", "json"]
        if session_id:
            cmd.extend(["-s", session_id])
        return cmd


def main():
    engine = OpenCodeEngine()
    parser = argparse.ArgumentParser(description="OpenCode Agent Controller")
    parser.add_argument("-t", "--task", nargs="?", const="", help="任务模式")
    parser.add_argument("--list", action="store_true", help="列出所有任务")
    parser.add_argument(
        "-ni", "--non-interactive", action="store_true", help="非交互模式"
    )
    parser.add_argument(
        "-y",
        "--yolo",
        action="store_true",
        default=True,
        help="开启 YOLO 模式 (默认开启)",
    )
    args, unknown = parser.parse_known_args()

    if args.list:
        show_tasks(label="Task List", file_suffix=TASK_FILE_SUFFIX)
        return

    if not require_engine_cli("opencode"):
        sys.exit(1)

    # 使用基类统一合成提示词
    full_prompt = engine.assemble_prompt(task=" ".join(unknown))

    if args.task is not None:
        task_prompt = handle_task_mode(
            args.task, label="Task", file_suffix=TASK_FILE_SUFFIX
        )
        if task_prompt:
            full_prompt = f"{full_prompt}\n\n{task_prompt}"

    resource_lock = engine.acquire_resource_lock(
        Path.cwd() / ".opencode" / ".codeagent-session.lock"
    )
    try:
        # 使用临时文件引导模式，解决命令行超长问题
        concise_msg = engine.write_temp_prompt(full_prompt)

        # 统一技能链接 (挂载到 .opencode/skills)
        engine.ensure_skills_link(".opencode/skills")
        # 统一插件链接
        engine.ensure_plugins_link()

        # OpenCode 没有 settings.json 这个概念（在 opencode 1.18 的二进制里
        # 完全搜不到该文件名），它的钩子是插件模块导出的 JS 函数
        # (tool.execute.before / tool.execute.after)，不是 shell 命令。
        # 因此用生成的桥接插件来跑 CodeAgent 的 shell 钩子。
        resolved_hooks = engine.get_hooks_to_inject()
        engine.ensure_hooks_bridge(resolved_hooks)

        env = engine.env_manager.get_env()
        register_signal_handler()

        final_command = engine.build_command(concise_msg, args.non_interactive)
        print(f"🚀 Launching {engine.name}...")

        engine.run_shell(final_command, env)
    finally:
        try:
            # 1. 清理旧版本可能遗留的 settings.json 注入文件
            engine.restore_settings(".opencode/settings.json")
            # 2. 清理技能链接
            engine.cleanup_skills_link(".opencode/skills")
            # 3. 清理插件链接
            engine.cleanup_plugins_link()
            # 4. 使用基类统一清理临时提示词
            engine.cleanup_temp_prompt()
        finally:
            engine.release_resource_lock(resource_lock)


if __name__ == "__main__":
    main()
