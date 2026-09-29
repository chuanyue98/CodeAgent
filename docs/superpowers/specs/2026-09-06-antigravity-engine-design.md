# Google Antigravity (`agy`) 引擎接入设计规范

## 1. 背景与目标

Google 已停止面向个人的 Gemini Code Assist 客户端服务，全面由 **Google Antigravity (AGY)** 取代。本机环境中已部署 Antigravity CLI 工具 `agy`（版本 2.0+），其运行时数据位于 `~/.gemini/antigravity-cli/`，全局配置位于 `~/.gemini/config/`。

本项目旨在将已下线的 Gemini 引擎升级重构为现代化的 **Antigravity** 引擎：
- 主引擎标识为 `antigravity`，别名支持 `agy`；
- 作为一等公民引擎，接入 CLI 交互、MCP 同步管理、会话历史解析与恢复、Web 端 LaunchPad 及无人值守后台任务 (Headless Task)。

---

## 2. 架构设计与模块划分

### 2.1 系统常量与分类 (`core/constants.py`)
- `ENGINES`: 包含 `antigravity`。
- `HEADLESS_ENGINES`: 包含 `antigravity`（支持通过 `agy -p` 执行单轮及非交互后台任务）。
- `MCP_ENGINES`: 包含 `antigravity`（支持通过 `agy mcp` 命令及 `~/.gemini/config/mcp_config.json` 同步）。

### 2.2 CLI 入口与启动器
- **CLI 路由 (`core/cli/main.py`)**:
  - `ca antigravity [MESSAGE]`: 主入口。
  - `ca agy [MESSAGE]`: 别名入口，直接转发至 `start_antigravity.py`。
- **启动脚本 (`engines/start_antigravity.py`)**:
  - 继承 `BaseEngine`，可执行体映射到 `agy`。
  - 交互模式：若带有初始输入，透传 `-i "<message>"`；启用 YOLO 时附加 `--dangerously-skip-permissions`。
  - 单轮 / Headless 模式：`agy -p "<message>" --output-format json --dangerously-skip-permissions`。
  - 会话继续模式：若传入 session_id，追加 `--conversation <session_id>`。
- **环境检查 (`core/doctor.py`)**:
  - 在 `ENGINE_COMMANDS` 中添加 `"antigravity": ["agy", "agy.exe"]`。

### 2.3 会话历史发现与跨引擎解析 (`core/session_history/`)
- **存储路径**:
  - 汇总 SQLite：`~/.gemini/antigravity-cli/conversation_summaries.db`（包含 `conversation_id`, `title`, `workspace_uris`, `last_modified_time` 等字段）。
  - 完整会话记录：`~/.gemini/antigravity-cli/brain/<uuid>/.system_generated/logs/transcript.jsonl`（包含 `USER_INPUT`、`PLANNER_RESPONSE`、tool calls、思考链等）。
  - 备用历史日志：`~/.gemini/antigravity-cli/history.jsonl`。
- **解析器 (`core/session_history/parsers/antigravity_parser.py`)**:
  - 实现 `AntigravityParser`，解析 `transcript.jsonl`，提取用户消息、模型回复、工具调用步骤。
  - 从 `conversation_summaries.db` 快速检索会话元数据（标题、更新时间、工作区），缺失时回退到 transcript 首步提取。
- **转换写入器 (`core/session_history/writers/antigravity_writer.py`)**:
  - 将通用的 `Session` 模型结构序列化并保存到 `~/.gemini/antigravity-cli/brain/<uuid>/...`，允许将其它引擎（如 Claude/OpenCode）的会话转换到 Antigravity 中恢复。
- **会话恢复指令 (`core/services/resume_commands.py`)**:
  - 返回 `["agy", "--conversation", session_id]`。

### 2.4 MCP 协同服务 (`core/services/mcp_service.py`)
- Antigravity 原生提供 `agy mcp` CLI 工具，配置落地于 `~/.gemini/config/mcp_config.json`。
- 实现 `_list_antigravity()`, `_add_antigravity()`, `_remove_antigravity()`：
  - `list`: 优先解析 `~/.gemini/config/mcp_config.json` 中的 `mcpServers`（或解析 `agy mcp list` 输出）。
  - `add`: 调用 `agy mcp add <name> <commandOrUrl> [args...]`，若带有环境变量则添加 `--env KEY=val`。
  - `remove`: 调用 `agy mcp remove <name>`。

### 2.5 后台任务与单轮对话 (`core/services/runner_service.py`)
- 在 `TaskRunner` 与 `ChatRouter` 中，`antigravity` 使用：
  ```bash
  agy -p "<prompt>" --output-format json --dangerously-skip-permissions
  ```
  如果需要指定已有会话，附加 `--conversation <session_id>`。

### 2.6 前端适配 (`web/frontend/`)
- `components/terminalEngines.ts`: 注册 `antigravity` 引擎，设置品牌色（Cyan/Teal 或 Indigo 风格）。
- `utils/engines.ts`: `ENGINE_LABELS.antigravity = "Antigravity"`。
- `components/LaunchPad.tsx`: 主网格展示 Antigravity 卡片。

---

## 3. 测试与验收标准

1. **Lint 与风格检查**:
   - `uv run ruff check .` 全量通过，无告警。
2. **自动化单元测试**:
   - `tests/test_antigravity_parser.py`: 覆盖 Antigravity transcript 解析与 writer 导出。
   - `tests/test_resume_commands.py`: 断言 `resume_command("antigravity", ...)` 返回正确的 `agy --conversation` 结构。
   - `tests/test_mcp_service.py`: 验证 `antigravity` 的 MCP 增删查调用。
   - `tests/test_runner_service.py`: 验证 TaskRunner 正确组装 `agy` 命令行。
   - `uv run pytest` 全量回归测试通过。
3. **CLI 手动验证**:
   - `ca antigravity --help` / `ca agy --help` 正常显示并可执行。
