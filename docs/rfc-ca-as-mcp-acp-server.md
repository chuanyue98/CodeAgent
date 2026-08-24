# RFC:CodeAgent 作为 MCP/ACP Server

> **状态**:Draft(待评审)
> **日期**:2026-08-24
> **作者**:CodeAgent 维护者
> **范围**:`core/mcp_server/` 新包、`ca mcp serve` 命令、远期 ACP 路线
> **相关**:`core/services/mcp_service.py` · `core/skill_scanner.py` · `core/prompt_scanner.py` · `core/hook_scanner.py` · `core/cli/commands/mcp.py` · `docs/mcp-cli-spike-results.md`

## 1. 摘要

CodeAgent 目前是"引擎的包装器":把标准(prompts)、工具(skills)、护栏(hooks)注入各家 CLI 引擎。这个模式依然成立,但引擎的形态已经多元化——CLI、headless 服务、ACP 协议、规则文件(App 端 IDE)。为了让 CodeAgent 的"标准层"不被任何引擎形态绑架,本 RFC 提出一个方向:

**让 CodeAgent 自身成为 MCP server(以及远期 ACP agent),把 skills / prompts / hooks 以标准化原语对外暴露。任何支持 MCP 的客户端(Claude Code、Cursor、Trae、CodeBuddy、ChatGPT……)连上 `ca mcp serve`,就能直接消费 CodeAgent 的工程标准,而不再需要先注册成某个引擎的子进程。**

一句话:从"把标准注入别人的引擎"到"把标准做成一个服务,让引擎来连我们"。

## 2. 背景与动机

### 2.1 引擎形态正在多元化(2026-08 实测)

| 形态 | 代表 | 对 CodeAgent 的意义 |
|---|---|---|
| 传统 CLI | claude、codex、qwen、traecli、cursor agent | 现有包装模式继续有效 |
| headless 服务 | `codebuddy --print/--serve`、`agent -p --force` | 新集成面,可脚本化 |
| 规则文件 | AGENTS.md、QWEN.md、CLAUDE.md、.cursor/rules | App 端 IDE 的事实标准,零依赖 |
| ACP 协议 | Zed / JetBrains 中的 claude、codex、gemini | "agent 嵌入编辑器"的新标准(见 §6) |

### 2.2 平台关停风险是真实的

Gemini CLI 已宣布 **2026-06-18 停止服务**,用户被强制迁移到 Antigravity CLI。这正是本项目"Prompt Sovereignty"(标准归我,引擎随便换)哲学的现实论据——但目前的实现仍然把标准绑定在"以子进程方式拉起某个 CLI"这一种形态上。若某天某引擎彻底关闭 CLI(或只出 App 端),注入链路就断了。**MCP server 形态让标准层的消费方与"某个具体引擎进程"彻底解耦。**

### 2.3 MCP 已事实成为行业标准

- 截至 2026-03,超过 **9700 万安装**,Claude、ChatGPT、VS Code、Cursor 全部支持;OpenAI 已弃用 Assistants API 转投 MCP。
- 官方 Python SDK **v2.0.0**(2026-07-28 随规范修订发布),支持 stdio / Streamable HTTP 双传输。
- 三大原语:**Tools(动作)、Resources(上下文)、Prompts(模板)**——与 CodeAgent 的 skills(动作)/ prompts(上下文+模板)/ hooks(护栏)几乎一一对应。

### 2.4 现状差距

`core/services/mcp_service.py` 目前只做**客户端管理**(把 MCP server 配置同步进 4 个引擎的各自配置),CodeAgent 从没有过 **server 身份**。本 RFC 补齐这一半。

## 3. 目标与非目标

### 目标

- `ca mcp serve`:以 stdio(默认)和 Streamable HTTP 两种传输运行 MCP server。
- 把 CodeAgent 的资源按 MCP 原语暴露:**skills → tools + resources,prompts → prompts + resources,hooks → 受控工具**。
- 与现有 `config.groups` 资源组绑定(`--group`),只暴露当前组挂载的资源。
- 提供 MCP Inspector 可验证、真实客户端可连接的 MVP。

### 非目标(本期)

- ❌ 不实现 ACP server(见 §6,列为远期决策点)。
- ❌ 不建立自研 agent loop(现状:包装官方 CLI;依赖里的 `claude-agent-sdk` 是未来选项)。
- ❌ 不替代现有 CLI 包装模式——MCP server 是**增量通道**,不是替代。
- ❌ 不做 Web UI 管理页(可复用现有 8524 仪表盘,但不在本期)。

## 4. 现状盘点(代码级)

| 现有模块 | 能力 | 复用方式 |
|---|---|---|
| `core/skill_scanner.py` | 扫描 skills → `{category: [skill names]}`,SKILL.md 判定 | 直接复用,注册 tools |
| `core/prompt_scanner.py` | 扫描 prompts → `{group: [stems]}`,跳过 README/IMPLEMENTATION_PLAN | 直接复用,注册 resources/prompts |
| `core/hook_scanner.py` | 扫描 hooks → metadata.json(event/command),含 `{hook_dir}` 占位符替换 | 直接复用,注册受控工具 |
| `core/services/mcp_service.py` | MCP **client** 管理(同步到 4 引擎) | 反向借力:serve 起来后,可用它把 `ca` 自己注册进 claude/codex 等引擎 |
| `core/cli/commands/mcp.py` | `ca mcp list/add/remove/sync` 命令组 | 扩展新子命令 `serve` |
| `core/services/runner_service.py` / `task_service.py` | 任务子进程管理、任务执行 | task tools 的执行后端 |
| `core/web/`(FastAPI,8524) | 仪表盘/API | 独立进程,不耦合;工具函数可共享 |

**关键结论:所有扫描与执行底座都已有,新增量集中在"协议适配层"(`core/mcp_server/`),不触碰现有架构。**

## 5. 设计:MCP Server

### 5.1 命令与传输

```bash
ca mcp serve                                  # stdio(默认,供桌面工具子进程启动)
ca mcp serve --transport http --port 8525     # Streamable HTTP,远程/多客户端
ca mcp serve --transport http --port 8525 --host 0.0.0.0
ca mcp serve --group work                     # 只暴露 work 组的资源
```

- **stdio**:桌面客户端(Claude Desktop、Cursor、CodeBuddy、Trae)以子进程方式拉起,零配置。
- **Streamable HTTP**:多客户端/远程场景;MCP 2026 规范已用 Streamable HTTP 取代旧 SSE 传输,直接实现新传输,不做 SSE。
- 默认端口 **8525**(避开 Web UI 的 8524)。

### 5.2 原语映射(核心)

#### Tools —— skills、tasks、hooks 的动作面

| MCP Tool | 映射 | 说明 |
|---|---|---|
| `skill.list` | 扫描结果 | `{category: [names]}` 直出 |
| `skill.run` | skill `scripts/` 执行 | 参数:`category/name` + 透传参数;解析 SKILL.md frontmatter 得执行入口 |
| `task.list` / `task.run` | `tasks/*.md` 蓝图 | 复用 `task_service`/`runner_service`,支持 `--dry-run` |
| `hook.fire` | hook metadata 的 command | 事件参数:`before_tool` / `after_tool`;受控(见 §5.4) |
| `engine.list` | `core.constants.ENGINES` | 元信息:CodeAgent 认识哪些引擎 |
| `group.info` | 当前 `--group` 的挂载清单 | skills/prompts/hooks/plugins 四类一览 |

#### Resources —— 工程之魂的上下文面

| URI 模式 | 内容 |
|---|---|
| `ca://prompts/{group}/{stem}` | prompt markdown **原文**(general.basic.md 等) |
| `ca://skills/{category}/{name}/SKILL.md` | skill 指令原文 |
| `ca://skills/{category}/{name}/scripts` | scripts 目录清单(不执行) |
| `ca://hooks/{category}/{name}` | hook metadata.json 原文 |
| `ca://config/groups` | 当前资源组配置 |
| `ca://config/registry` | 已注册项目列表 |

> 统一使用 `ca://` 命名空间,避免与客户端自身资源冲突。

#### Prompts —— 一键注入模板

- 把 `--group` 挂载的 prompt 组注册为 MCP **prompt 原语**(如 `ca://prompts/base`),客户端可像用自带模板一样直接插入 CodeAgent 的工程之魂,再由客户端自己的 agent 继续执行。
- 这实现了"标准注入"的**通用化**:不再依赖任何引擎的 system-prompt 注入机制。

### 5.3 组绑定

`--group` 决定暴露范围,默认取 `config.json` 中 `project_registry` 匹配当前目录的组(与现有引擎启动逻辑一致);未匹配时默认 `codeagent`。暴露内容严格等于该组挂载项,不越权。

### 5.4 安全模型

| 层面 | 规则 |
|---|---|
| stdio | 本地信任模型;写类工具(`skill.run`、`task.run`、`hook.fire`)默认要求客户端 `tools/call` 携带确认标志,或由 `--allow-write` 显式开启 |
| HTTP | **必须** token(`CA_MCP_TOKEN` 或 `--token`),启动时生成/校验;建议只监听回环地址 |
| 路径 | 所有文件访问经 `Path.resolve()` 后校验在 `config.registry` 或 CWD 白名单内 |
| 凭证 | server **永不**接触或转发任何 API key/凭证;不读取引擎的 auth 文件 |
| 审计 | 每次 `tools/call` 记录 `(tool, args, caller)` 到现有 analytics 管道 |
| 危险操作 | `hook.fire` 这类任意命令执行工具,默认仅对 `--trust-hooks` 显式放行 |

### 5.5 与现有 web/CLI 的关系

- 独立进程、独立端口;不修改 8524 仪表盘的启动路径。
- `ca doctor` 增加健康检查:`ca mcp serve --check`(或 `ca doctor` 探测 8525),复用 `find_available_port`/`is_tcp_port_open`。
- 注册到自家引擎:`ca mcp add claude ca --url http://127.0.0.1:8525`——用现有的 `mcp_service.add_server()` 即可闭环(吃自己的狗粮)。

## 6. 设计:ACP 路线(远期)

### 6.1 ACP 现状(2026-08)

- **ACP = Editor ↔ Agent 协议**(LSP 类比);**MCP = Agent ↔ Tools**,两者叠加、不竞争:Zed 经 ACP 拉起 Claude Code,Claude Code 再经 MCP 连数据库。
- v1 由 Zed 于 2025-08 发布;JetBrains 2025-09 加入联合主导;ACP Registry 2026-01 上线,现有 **60+ agents、12+ 编辑器**;Devin Desktop、AWS Kiro 已原生支持。
- 实现 ACP server 的前提是"自己是 agent"(有 agent loop、能自主决策)。

### 6.2 CodeAgent 的两种 ACP 身份

| 选项 | 描述 | 前提 | 评估 |
|---|---|---|---|
| **A:ACP agent** | CodeAgent 作为 ACP server 嵌入 Zed/JetBrains,用户直接在编辑器里用 CodeAgent | 需要自研/引入 agent loop(如 `claude-agent-sdk`,依赖已存在) | 工作量最大;与项目"包装他人 CLI"哲学冲突 |
| **B:ACP client / 管理器** | CodeAgent 把 Zed/JetBrains 里注册的 ACP agent 纳入"引擎矩阵",作为新的引擎形态适配 | 需做 ACP client(JSON-RPC over stdio) | 与现有 engine adapter 模式一致,是自然演进 |

### 6.3 决策建议

- **本期不做 ACP**。理由:MCP server 已经覆盖"标准层对外服务化"的核心价值,且 ACP 生态(尤其 VS Code 侧)仍未定型。
- **M1-M3 完成后**再评估:若市场确认"编辑器内直接用 CodeAgent"是高频需求,优先走 **选项 B**(ACP client),复用 `core/engine_base.py` 的 adapter 模式,新增 `engines/start_acp.py`。
- 预留适配点:`core/services/agent_protocol.py` 已把引擎差异抽象为统一协议,ACP 可作为新 adapter 接入,无需改动核心。

## 7. 依赖与实现计划

### 依赖

```bash
uv add "mcp[cli]"        # 官方 Python SDK v2.0+(2026-07-28 规范)
```

> ⚠️ v2.0 是协议层重写,1.x 教程不适用;实现时以 SDK v2 的 `MCPServer`/FastMCP 风格 API 为准,先做 15 行 MVP 验证 API 形态再铺开。

### 新增文件

```text
core/mcp_server/
├── __init__.py
├── server.py        # 启动/传输选择/生命周期(stdio | streamable-http)
├── tools.py         # skill/task/hook 的 tools 注册
├── resources.py     # ca:// 资源 URI 解析
├── prompts.py       # prompt 原语注册
├── auth.py          # token 校验、写操作放行、审计
└── health.py        # --check 自检
```

### 里程碑

| 里程碑 | 内容 | 验证 |
|---|---|---|
| **M1** | `ca mcp serve` stdio + 只读原语(prompts/resources + skill.list/group.info) | MCP Inspector 通过 |
| **M2** | 写类 tools(`skill.run`、`task.run`、`hook.fire`) + 安全校验 | 在 CodeBuddy/Trae/Cursor 里真实调用 |
| **M3** | Streamable HTTP + token 鉴权 + `ca doctor` 检查 | 远程客户端 + 审计日志 |
| **M4** | 决策点:ACP 路线(选项 A/B)评审 | — |

## 8. 兼容矩阵(预期)

| 客户端 | stdio | Streamable HTTP | 备注 |
|---|---|---|---|
| Claude Desktop / Claude Code | ✅ | ✅ | `claude mcp add` 原生支持 |
| Cursor | ✅ | 视版本 | `.cursor/mcp.json` |
| Trae | ✅ | 视版本 | TraeCode 配置 MCP |
| CodeBuddy | ✅ | ✅ | `codebuddy mcp` 配置 |
| ChatGPT / 其他 | — | ✅ | HTTP 端点 |
| Zed(JetBrains 同理) | 经 ACP agent 间接 | — | 见 §6 |

## 9. 风险与开放问题

1. **SDK v2 API 稳定性**:2026-07-28 刚发布,实现以 SDK v2 为准并在 pyproject 锁版本;M1 前先跑官方 quickstart 验证。
2. **`skill.run` 的环境污染**:skill scripts 在子进程执行,需继承现有 `runner_service` 的孤儿回收/超时机制;禁止继承 server 自身的 stdin/stdout(stdio 传输下会污染协议流)。
3. **Windows stdio 兼容**:pty/编码问题已有前科(见 `fix/opencode-conversion-and-windows-test-fixes`),M1 在 Windows 上先行验证。
4. **命名冲突**:`ca mcp serve` 与现有 `ca mcp` 子命令共存,注意 help 文案与 i18n(`core/i18n.py`)。
5. **写权限边界**:`--allow-write` / `--trust-hooks` 的默认值需谨慎——默认**只读**,这是安全底线。
6. **与 `ca rules sync`(规则文件注入)的关系**:两者互补——MCP server 面向"活的连接",规则文件面向"零依赖的静态注入"。建议 M3 后评估是否合入同一 RFC 或拆为独立 RFC。

## 10. 结论

MCP server 是 CodeAgent 从"包装器"走向"标准服务商"的最低成本路径:所有扫描/执行底座已存在,新增量只是协议适配层(约 4-6 个模块)。它不推翻现有 CLI 模式,而是为"只有 App 端/只有协议接口"的新形态引擎提供一个统一入口——**这正是项目哲学"引擎随便换"的终极形态:连进程都不用拉,标准本身就是服务。**

---

### 附录:配套能力 `ca rules sync`(简述)

作为 MCP server 的零依赖补充,把当前组挂载的 prompts/skills 合成输出为标准规则文件,让 App 端 IDE 无需任何协议即可继承:

```bash
ca rules sync --format agents.md          # AGENTS.md(行业收敛标准)
ca rules sync --format qwen.md            # QWEN.md
ca rules sync --format cursor             # .cursor/rules/*
ca rules sync --format claude             # CLAUDE.md
```

实现可复用 `prompt_kit.py` 的合成逻辑,新增 `core/rules_exporter.py`。是否与本 RFC 合并实施,评审时定。
