"""CodeAgent MCP server — 把项目资产按 MCP 标准暴露为 tools / resources。

与 :mod:`core.services.mcp_service`(客户端管理:把外部 MCP server 配置进各引擎)
互补。本模块是**服务端**:任何支持 MCP 的客户端(CodeBuddy / Trae / Cursor /
claude / codex ...)都可以连上来直接消费 CodeAgent 的技能(skills)。

当前暴露:
- 只读工具(始终可用): ``skill_list`` / ``skill_read``
- 资源: ``ca://skills``(索引)、``ca://skill/{name}``(动态模板,SKILL.md 原文)
- 写类工具(需 ``--allow-write`` 才注册): ``skill_run`` / ``task_run``
- 危险工具(需 ``--trust-hooks`` 才注册): ``hook_fire``(任意命令执行)

安全底线:默认只读 —— 不注册任何写工具,不接触任何 API 密钥。写工具
执行时子进程**不继承** server 自身的 stdin/stdout,避免在 stdio 传输下污染
协议流。

设计要点:
- 技能目录结构 ``skills/<category>/<skill>/SKILL.md``,frontmatter 提供
  ``name`` / ``description``(与 :class:`core.skill_scanner.SkillScanner` 的
  发现逻辑一致)。
- ``--group`` 绑定复用 ``config.json`` 里 ``groups.<name>.skills`` 的
  ``"category/name"`` 列表,未指定组时挂载全部技能。
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from core.host_env import child_environ
from core.resource_locator import get_bundled_resource_root

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - 依赖缺失时给出可读错误
    FastMCP = None  # type: ignore[assignment,misc]

SERVER_NAME = "codeagent"
SERVER_INSTRUCTIONS = (
    "CodeAgent 技能库与跨引擎协作服务。默认只读,提供 skill_list / skill_read 两个工具,"
    "以及 ca://skills 与 ca://skill/<name> 资源,所有内容来自磁盘上的 SKILL.md 原文。"
    "以 --allow-write 启动时额外提供 skill_run / task_run 与跨引擎委派工具;"
    "以 --trust-hooks 启动时再额外提供 hook_fire(执行 hook 脚本)。"
)

#: ``--delegation`` 模式（ca 启动引擎时动态挂载的就是它）交给宿主模型的说明。
#: 提示词注入已经取消，这是模型得知"怎么委派"的唯一渠道。
DELEGATION_INSTRUCTIONS = """CodeAgent 跨引擎协作：把子任务交给另一个编码引擎（claude / codex / opencode / codebuddy / antigravity）在后台完成，用法同你自己的后台子代理。

- 用户点名要某个引擎做事（"让 codex review 一下""让 claude 设计这块"），或有边界清晰、可以并行的子任务时，调用 ca_delegate。它立即返回 run_id，不会阻塞你。
- 发起后继续做你手头的事；需要结果时调用 ca_delegate_wait(run_id)。它最多等 45 秒，还没结束就返回 running，稍后再调。不要在同一个 run 上连续空等。
- mode="review"：只读审查当前未提交的改动，在带着这些改动的一次性 git worktree 里进行，不会碰主工作区，结果是问题列表。
- mode="write"：默认在当前工作区就地修改；isolate_worktree=True 则在独立分支上改，结果里会给出分支名。
- 子引擎看不到你的对话，instruction 要写清背景、目标、验收标准和相关文件。
- 拿到结果后自己核实（看 diff、跑测试），再向用户汇报。"""


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """极简 frontmatter 解析,返回 (meta, body)。无 frontmatter 时返回 ({}, 原文)。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip("\"'")
    return meta, parts[2].strip()


def discover_skills(
    skills_root: Path,
    config: dict | None = None,
    group: str | None = None,
) -> list[dict]:
    """扫描 ``skills/<category>/<skill>/SKILL.md``,返回技能元信息列表。

    Args:
        skills_root: 技能根目录(含 category 子目录)。
        config: 应用配置(config.json 内容);提供时才应用 ``group`` 过滤。
        group: 配置组名。指定时只挂载 ``config["groups"][group]["skills"]``
            里的技能(条目格式 ``"category/name"``);为 ``None`` 时挂载全部。

    Returns:
        每个技能一个 dict: ``name`` / ``title`` / ``description`` /
        ``category`` / ``path``。
    """
    allowed: set[str] | None = None
    if group is not None:
        if not config:
            return []
        entries = (config.get("groups") or {}).get(group, {}).get("skills") or []
        allowed = {str(entry) for entry in entries}

    skills: list[dict] = []
    if not skills_root.exists():
        return skills
    for category_dir in sorted(skills_root.iterdir()):
        if not category_dir.is_dir():
            continue
        for skill_dir in sorted(category_dir.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            if (
                allowed is not None
                and f"{category_dir.name}/{skill_dir.name}" not in allowed
            ):
                continue
            try:
                text = skill_md.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            meta, body = _parse_frontmatter(text)
            first_line = next((line for line in body.splitlines() if line.strip()), "")
            skills.append(
                {
                    "name": skill_dir.name,
                    "title": meta.get("name", skill_dir.name),
                    "description": meta.get(
                        "description", first_line.strip("# -")[:80]
                    ),
                    "category": category_dir.name,
                    "path": str(skill_md),
                }
            )
    return skills


def _find_skill(skills_root: Path, name: str) -> Path | None:
    """按技能目录名定位 SKILL.md(跨 category 查找)。"""
    if not skills_root.exists():
        return None
    for category_dir in skills_root.iterdir():
        if not category_dir.is_dir():
            continue
        candidate = category_dir / name / "SKILL.md"
        if candidate.is_file():
            return candidate
    return None


def _find_hook(hooks_root: Path, name: str) -> Path | None:
    """按 hook 名定位 hook.py(跨 category 查找)。name 可为 ``category/hook`` 或 ``hook``。"""
    if not hooks_root.exists():
        return None
    # 支持 "category/hook" 直接定位
    direct = hooks_root / name / "hook.py"
    if direct.is_file():
        return direct
    for category_dir in sorted(hooks_root.iterdir()):
        if not category_dir.is_dir():
            continue
        candidate = category_dir / name / "hook.py"
        if candidate.is_file():
            return candidate
    return None


def _resolve_skill_script(skill_dir: Path, script_arg: str | None) -> Path | None:
    """定位要执行的脚本。

    - ``script_arg`` 给定时,解析后必须仍落在 ``skill_dir`` 内(防路径穿越),否则抛 ``ValueError``。
    - 否则自动挑选:``scripts/run.{py,sh,cmd}`` 优先,退化为 ``scripts/`` 下唯一个文件。
    - 都没有则返回 ``None``(交给调用方做"返回指引"的安全回退)。
    """
    scripts_dir = skill_dir / "scripts"
    if script_arg:
        candidate = (skill_dir / script_arg).resolve()
        if not str(candidate).startswith(str(skill_dir.resolve())):
            raise ValueError(f"脚本路径越界: {script_arg}")
        return candidate
    for entry in ("run.py", "run.sh", "run.cmd"):
        auto = scripts_dir / entry
        if auto.is_file():
            return auto.resolve()
    if scripts_dir.is_dir():
        files = [p for p in scripts_dir.iterdir() if p.is_file()]
        if len(files) == 1:
            return files[0].resolve()
    return None


def _script_command(script_path: Path) -> list[str]:
    """根据扩展名选解释器。"""
    suffix = script_path.suffix.lower()
    if suffix == ".py":
        return [sys.executable, str(script_path)]
    if suffix == ".sh":
        return ["bash", str(script_path)]
    if suffix == ".cmd":
        return ["cmd", "/c", str(script_path)]
    return [str(script_path)]


def _run_script(
    script_path: Path, args: str, cwd: Path, timeout: int = 300
) -> tuple[str, int]:
    """在干净子进程中执行脚本。

    不继承 server 自身的 stdin/stdout/stderr(尤其 stdio 传输下必须如此,否则会
    污染 JSON-RPC 通道)。返回 ``(combined_output, exit_code)``;输出截断到 64KB。
    """
    cmd = _script_command(script_path) + shlex.split(args or "")
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=child_environ(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    out = (proc.stdout or "")[: 64 * 1024]
    return out, proc.returncode


def _append_audit(root_dir: Path | None, tool: str, args: dict) -> None:
    """轻量审计:追加一行 JSONL 到 ``<root>/.ca_task_logs/mcp_audit.log``。"""
    root = root_dir or Path.cwd()
    log_dir = root / ".ca_task_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.time(),
        "tool": tool,
        "args": args,
    }
    try:
        with (log_dir / "mcp_audit.log").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _register_delegation_tools(
    server: FastMCP, root_dir: Path | None, group: str | None
) -> None:
    """跨引擎委派工具。当前已在委派深度上限（本身就是被委派出来的）时一个都不注册。"""
    from core.delegation_depth import may_delegate

    if not may_delegate():
        return

    from core.services import delegation_runs

    def workspace() -> Path:
        return root_dir or Path.cwd()

    @server.tool()
    def ca_delegate(
        engine: str,
        instruction: str,
        mode: str = "write",
        target_paths: list[str] | None = None,
        isolate_worktree: bool = False,
        timeout_seconds: int = delegation_runs.DEFAULT_TIMEOUT_SECONDS,
    ) -> str:
        """把子任务交给另一个引擎在后台执行，立即返回 run_id。

        Args:
            engine: claude / codex / opencode / codebuddy / antigravity。
            instruction: 子引擎看不到你的对话：写清背景、目标、验收标准。
            mode: "write" 改代码；"review" 只读审查当前未提交的改动。
            target_paths: 相关文件或目录（可选）。
            isolate_worktree: write 模式下改到独立的 git worktree 分支上。
            timeout_seconds: 子引擎最长运行时间，默认 1800。
        """
        # 不写 .ca_task_logs 审计：这个服务随每次 ca 启动挂进用户项目，委派的
        # 全部信息已记在 ~/.codeagent/delegations/<run_id>/task.json。
        try:
            run_id = delegation_runs.start_delegation(
                engine,
                instruction,
                workspace=workspace(),
                mode=mode,
                isolate=isolate_worktree,
                target_paths=target_paths,
                timeout=timeout_seconds,
                group=group or "common",
            )
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        return json.dumps(
            {
                "run_id": run_id,
                "status": "started",
                "next": "继续你的工作；需要结果时调用 ca_delegate_wait(run_id)",
            },
            ensure_ascii=False,
        )

    @server.tool()
    def ca_delegate_wait(run_id: str, timeout_seconds: int = 45) -> str:
        """等待一个委派，最多 timeout_seconds 秒（上限 45）。

        结束了就返回完整结果（summary / files_changed / diff / error），否则返回
        status=running，稍后再调。
        """
        try:
            run = delegation_runs.wait_run(run_id, timeout=min(timeout_seconds, 45))
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        return json.dumps(run, ensure_ascii=False, indent=2)

    @server.tool()
    def ca_delegate_list() -> str:
        """列出当前工作区最近的委派及其状态。"""
        return json.dumps(
            delegation_runs.list_runs(workspace()), ensure_ascii=False, indent=2
        )

    @server.tool()
    def ca_delegate_stop(run_id: str) -> str:
        """终止一个仍在运行的委派（连同它拉起的子引擎）。"""
        try:
            stopped = delegation_runs.stop_run(run_id)
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        return json.dumps({"run_id": run_id, "stopped": stopped}, ensure_ascii=False)


def build_delegation_server(root_dir: Path | None = None) -> FastMCP:
    """ca 启动引擎时动态挂载的服务：只有委派工具，技能已由引擎原生挂载。"""
    if FastMCP is None:  # pragma: no cover
        raise RuntimeError("mcp SDK 未安装:请先 uv add mcp")
    server = FastMCP(SERVER_NAME, instructions=DELEGATION_INSTRUCTIONS)
    _register_delegation_tools(server, root_dir, os.environ.get("CA_PROJECT_GROUP"))
    return server


def build_server(
    config: dict | None = None,
    group: str | None = None,
    skills_root: Path | None = None,
    *,
    allow_write: bool = False,
    trust_hooks: bool = False,
    root_dir: Path | None = None,
) -> FastMCP:
    """构建 FastMCP server,把 skills 暴露为 tools 和 resources。

    Args:
        config: 应用配置;传了才支持 ``group`` 过滤。
        group: 配置组名,见 :func:`discover_skills`。
        skills_root: 技能根目录,默认取资源根下的 ``skills``。
        allow_write: 注册写类工具 ``skill.run`` / ``task.run``。
        trust_hooks: 注册危险工具 ``hook.fire``(隐含要求 ``allow_write``)。
        root_dir: 项目根,供 ``task.run`` 取 TaskRunner、审计日志落盘。
    """
    if FastMCP is None:  # pragma: no cover - 由 CLI 命令的异常路径兜底
        raise RuntimeError("mcp SDK 未安装:请先 uv add mcp")

    root = skills_root or (get_bundled_resource_root() / "skills")
    server = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)

    @server.tool()
    def skill_list() -> str:
        """列出 CodeAgent 提供的全部技能(name / title / description / category / path)。"""
        return json.dumps(
            discover_skills(root, config, group), ensure_ascii=False, indent=2
        )

    @server.tool()
    def skill_read(name: str) -> str:
        """读取指定技能的 SKILL.md 全文(含 frontmatter)。name 为技能目录名,如 'commit-message'。"""
        skill_md = _find_skill(root, name)
        if skill_md is None:
            return f"技能不存在: {name}(可用 skill_list 查看全部)"
        return skill_md.read_text(encoding="utf-8")

    @server.resource("ca://skills")
    def skills_index() -> str:
        """技能总览:每个技能的 name + description。"""
        lines = ["# CodeAgent Skills\n"]
        for s in discover_skills(root, config, group):
            lines.append(f"- **{s['name']}**({s['category']}): {s['description']}")
        return "\n".join(lines)

    @server.resource("ca://skill/{name}")
    def skill_doc(name: str) -> str:
        """指定技能的 SKILL.md 原文。"""
        skill_md = _find_skill(root, name)
        if skill_md is None:
            return f"技能不存在: {name}"
        return skill_md.read_text(encoding="utf-8")

    if allow_write or trust_hooks:

        @server.tool()
        def skill_run(name: str, args: str = "", script: str | None = None) -> str:
            """执行一个技能。name 为技能目录名(如 'commit-message')。

            优先运行 ``script`` 参数指定的脚本(必须位于技能目录内),否则自动挑选
            ``scripts/run.*`` 或该目录下唯一的脚本文件。若技能无可执行脚本,则回退为
            返回 SKILL.md 原文作为操作指引。仅 --allow-write 时可用。
            """
            _append_audit(
                root_dir, "skill.run", {"name": name, "args": args, "script": script}
            )
            skill_md = _find_skill(root, name)
            if skill_md is None:
                return f"技能不存在: {name}(可用 skill_list 查看全部)"
            skill_dir = skill_md.parent
            try:
                target = _resolve_skill_script(skill_dir, script)
            except ValueError as exc:
                return f"✗ {exc}"
            if target is None:
                return (
                    skill_md.read_text(encoding="utf-8")
                    + "\n\n[该技能无可执行脚本,以上为操作指引]"
                )
            out, code = _run_script(target, args, cwd=skill_dir)
            return f"exit={code}\n---\n{out}"

        @server.tool()
        def task_run(task_name: str, engine: str, group: str | None = None) -> str:
            """后台启动一个 CodeAgent 任务。仅 --allow-write 时可用。

            委托已有的 TaskRunner,返回 run id 与状态摘要。engine 取 claude/codex/
            opencode/codebuddy 之一;group 缺省为 'common'。
            """
            _append_audit(
                root_dir,
                "task.run",
                {"task_name": task_name, "engine": engine, "group": group},
            )
            from core.services.runner_service import TaskRunner

            runner = TaskRunner(root_dir or Path.cwd())
            status = runner.run_task(task_name, engine, group=group or "common")
            return json.dumps(
                {
                    "task_id": status.task_id,
                    "engine": status.engine,
                    "status": status.status,
                    "pid": status.pid,
                    "log_path": status.log_path,
                },
                ensure_ascii=False,
            )

        _register_delegation_tools(server, root_dir, group)

        @server.tool()
        def ca_handoff_session(
            target_engine: str,
            reason: str = "",
            source_engine: str | None = None,
        ) -> str:
            """当遇到上下文瓶颈、限流或死循环时,主动将当前会话打包并移交给目标引擎继续执行。

            Args:
                target_engine: 目标引擎名称 (claude / codex / opencode / antigravity / codebuddy)。
                reason: 移交原因与当前进展摘要。
                source_engine: 源引擎名称(可选,缺省自动检测)。
            """
            _append_audit(
                root_dir,
                "ca_handoff_session",
                {
                    "target_engine": target_engine,
                    "reason": reason,
                    "source_engine": source_engine,
                },
            )
            from core.services.delegation_service import handoff_session

            try:
                result = handoff_session(
                    target_engine=target_engine,
                    source_engine=source_engine,
                    project_path=root_dir,
                    reason=reason,
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            except Exception as exc:
                return json.dumps(
                    {"status": "failed", "error": str(exc)}, ensure_ascii=False
                )

    if trust_hooks:

        @server.tool()
        def hook_fire(hook_name: str, event_json: str = "{}") -> str:
            """执行一个 hook 脚本(任意命令执行,最高危)。仅 --trust-hooks 时可用。

            hook_name 为 hook 目录名(可带 category 前缀,如 'base/branch-protection')。
            event_json 作为 stdin 传给 hook.py。返回执行输出与退出码。
            """
            _append_audit(root_dir, "hook.fire", {"hook_name": hook_name})
            hooks_root = get_bundled_resource_root() / "hooks"
            hook_py = _find_hook(hooks_root, hook_name)
            if hook_py is None:
                return f"hook 不存在: {hook_name}"
            try:
                json.loads(event_json)
            except json.JSONDecodeError:
                return "✗ event_json 不是合法 JSON"
            proc = subprocess.run(
                _script_command(hook_py),
                input=event_json,
                env=child_environ(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
            out = (proc.stdout or "")[: 64 * 1024]
            return f"exit={proc.returncode}\n---\n{out}"

    return server


def serve(
    config: dict | None = None,
    group: str | None = None,
    skills_root: Path | None = None,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8525,
    *,
    allow_write: bool = False,
    trust_hooks: bool = False,
    root_dir: Path | None = None,
) -> None:
    """启动 MCP server(阻塞)。

    Args:
        config / group / skills_root: 见 :func:`build_server`。
        transport: ``"stdio"``(默认,桌面工具子进程拉起)或 ``"http"``。
        host / port: HTTP 模式下的绑定地址与端口。
        allow_write / trust_hooks / root_dir: 见 :func:`build_server`。
    """
    server = build_server(
        config,
        group,
        skills_root,
        allow_write=allow_write,
        trust_hooks=trust_hooks,
        root_dir=root_dir,
    )
    if transport == "http":
        import uvicorn

        print(f"codeagent MCP server listening on http://{host}:{port}", flush=True)
        uvicorn.run(
            server.streamable_http_app(), host=host, port=port, log_level="warning"
        )
    else:
        server.run(transport="stdio")


def main() -> None:
    """命令行入口(供 ``python -m core.services.mcp_server_service`` 或 MCP 客户端直接拉起)。"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the CodeAgent MCP server (read-only by default)"
    )
    parser.add_argument(
        "--http", action="store_true", help="Streamable HTTP mode (default: stdio)"
    )
    parser.add_argument(
        "--port", type=int, default=8525, help="HTTP port (default: 8525)"
    )
    parser.add_argument(
        "--group", default=None, help="config group to filter skills by"
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Register skill.run / task.run (execute skills & tasks)",
    )
    parser.add_argument(
        "--delegation",
        action="store_true",
        help="Only the cross-engine delegation tools (what ca mounts into engines)",
    )
    parser.add_argument(
        "--trust-hooks",
        action="store_true",
        help="Also register hook.fire (arbitrary command execution; implies --allow-write)",
    )
    args = parser.parse_args()
    if args.delegation:
        build_delegation_server().run(transport="stdio")
        return
    allow_write = args.allow_write or args.trust_hooks
    serve(
        transport="http" if args.http else "stdio",
        group=args.group,
        port=args.port,
        allow_write=allow_write,
        trust_hooks=args.trust_hooks,
    )


if __name__ == "__main__":
    main()
