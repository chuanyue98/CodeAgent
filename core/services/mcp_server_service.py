"""CodeAgent MCP server — 把项目资产按 MCP 标准暴露为 tools / resources。

与 :mod:`core.services.mcp_service`(客户端管理:把外部 MCP server 配置进各引擎)
互补。本模块是**服务端**:任何支持 MCP 的客户端(CodeBuddy / Trae / Cursor /
claude / codex ...)都可以连上来直接消费 CodeAgent 的技能(skills)。

当前暴露(只读):
- tools: ``skill_list`` / ``skill_read``
- resources: ``ca://skills``(索引)、``ca://skill/{name}``(动态模板,SKILL.md 原文)

安全底线:默认只读 —— 不提供任何写操作,不接触任何 API 密钥。

设计要点:
- 技能目录结构 ``skills/<category>/<skill>/SKILL.md``,frontmatter 提供
  ``name`` / ``description``(与 :class:`core.skill_scanner.SkillScanner` 的
  发现逻辑一致)。
- ``--group`` 绑定复用 ``config.json`` 里 ``groups.<name>.skills`` 的
  ``"category/name"`` 列表,未指定组时挂载全部技能。
"""

from __future__ import annotations

import json
from pathlib import Path

from core.resource_locator import get_bundled_resource_root

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - 依赖缺失时给出可读错误
    FastMCP = None  # type: ignore[assignment,misc]

SERVER_NAME = "codeagent"
SERVER_INSTRUCTIONS = (
    "CodeAgent 技能库只读服务。提供 skill_list / skill_read 两个工具,"
    "以及 ca://skills 与 ca://skill/<name> 资源。"
    "所有内容来自磁盘上的 SKILL.md 原文。"
)


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


def build_server(
    config: dict | None = None,
    group: str | None = None,
    skills_root: Path | None = None,
) -> FastMCP:
    """构建只读的 FastMCP server,把 skills 暴露为 tools 和 resources。

    Args:
        config: 应用配置;传了才支持 ``group`` 过滤。
        group: 配置组名,见 :func:`discover_skills`。
        skills_root: 技能根目录,默认取资源根下的 ``skills``。
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

    return server


def serve(
    config: dict | None = None,
    group: str | None = None,
    skills_root: Path | None = None,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8525,
) -> None:
    """启动 MCP server(阻塞)。

    Args:
        config / group / skills_root: 见 :func:`build_server`。
        transport: ``"stdio"``(默认,桌面工具子进程拉起)或 ``"http"``。
        host / port: HTTP 模式下的绑定地址与端口。
    """
    server = build_server(config, group, skills_root)
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
        description="Run the CodeAgent MCP server (read-only)"
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
    args = parser.parse_args()
    serve(transport="http" if args.http else "stdio", group=args.group, port=args.port)


if __name__ == "__main__":
    main()
