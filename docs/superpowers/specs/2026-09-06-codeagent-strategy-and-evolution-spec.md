# CodeAgent 战略定位与产品优化落地全景规范（Spec）

- **日期**: 2026-09-06
- **状态**: Approved (via `/grill-me` 深度访谈对齐)
- **文档编号**: SPEC-20260906-EVOLUTION

---

## 1. 战略定位：CodeAgent 存在的必要性

### 1.1 行业现状与开发者痛点
当前 AI 编程领域呈现**“大厂割据、各自为政”**的格局：
- **Anthropic** 主推 Claude Code（强于复杂规划与全流程交付，深度依赖自有 hooks/subagents）
- **OpenAI** 主推 Codex CLI（沙箱严密、TOML 配置体系、沉淀丰富）
- **Google** 主推 Antigravity (agy)（强调多子代理调度、技能体系与长会话上下文）
- **开源阵营** 主推 OpenCode（高灵活性、多模型直连）

**开发者的真实困境**：
1. **资产碎片化**：每个 CLI 工具的 Prompt、Skills、Hooks、MCP 配置格式均不互通，换一个工具就要重新配置一遍，开发者的数字资产被特定工具绑架。
2. **上下文孤岛**：一个会话在某个 CLI 中遇到长上下文衰减、模型限流或陷入逻辑死循环时，无法带着完整的分析状态无缝转移给另一个擅长的工具。
3. **协同割裂**：无法让“擅长写架构的 Claude”、“擅长查文档的 Antigravity”和“擅长单测生成的 Codex”在同一个工程项目里分工协作。

### 1.2 CodeAgent 的核心使命与生态位
> **CodeAgent 的定位：中立的「AI Engineering Shell（多引擎编排与统一工作台）」**

CodeAgent **不自建模型调用抽象层**（不与 LangGraph/PydanticAI 等底层框架竞争），也**不研发私有闭门模型**，而是专注于做各官方 CLI 进程的**“系统级调度中枢与资产保全层”**：
1. **资产主权（Asset Sovereignty）**：一次编写 Prompt/Skill/MCP，CodeAgent 负责自动抹平格式差异并实时双向同步到各引擎的原生配置文件中。
2. **状态连续（State Continuity）**：通过规范化的 Session 转换层（`ca switch`），实现任意两款 CLI 之间的会话上下文无缝迁移。
3. **跨引擎互通智能体（Inter-Engine Collaboration）**：提供低延迟、原生的伴生通信机制，使各个孤立的 CLI 能够互相唤起、互相委派、协同作战。

---

## 2. 核心技术架构：跨引擎底层互通与相互调用

为了实现“让各个 CLI 工具互通得更加底层、更加方便，还能相互调用”，本方案采用**“双层互通模型（Two-Tier Interoperability Model）”**。

```
                ┌─────────────────────────────────────────┐
                │          宿主引擎 (Caller CLI)          │
                │     (Claude Code / Antigravity / ...)    │
                └────────────────────┬────────────────────┘
                                     │ 1. 工具调用 (JSON-RPC)
                                     ▼
                ┌─────────────────────────────────────────┐
                │     CodeAgent 伴生 MCP (ca-mcp)         │
                │  - delegate_subtask(engine, task)       │
                │  - handoff_session(target_engine)       │
                └────────────────────┬────────────────────┘
                                     │ 2. 隔离调度
                                     ▼
                ┌─────────────────────────────────────────┐
                │        CodeAgent Orchestrator           │
                │  ┌───────────────────┐ ┌─────────────┐  │
                │  │ Git Worktree 管理 │ │ 会话与管道  │  │
                │  └─────────┬─────────┘ └──────┬──────┘  │
                └────────────┼──────────────────┼─────────┘
                             │ 创建分支隔离     │ 捕获标准输出/JSON
                             ▼                  ▼
                ┌─────────────────────────────────────────┐
                │          受委派引擎 (Worker CLI)        │
                │          (Codex / agy headless)         │
                └─────────────────────────────────────────┘
```

### 2.1 上层协议：伴生 MCP 服务 (`ca-mcp`)
各大主流 CLI（Claude Code、Codex、Antigravity、OpenCode）均已原生支持 **MCP（Model Context Protocol）** 客户端模式。

CodeAgent 在启动任意引擎时，将自身的轻量伴生服务（`ca-mcp`）自动注册至目标引擎的 MCP 配置中，暴露以下标准工具：

```json
[
  {
    "name": "ca_delegate_subtask",
    "description": "向其他专项引擎委派独立子任务（在隔离的工作区分支中运行），并返回执行摘要与代码 Diff",
    "parameters": {
      "type": "object",
      "properties": {
        "engine": {"type": "string", "enum": ["claude", "codex", "opencode", "antigravity"]},
        "instruction": {"type": "string", "description": "具体的子任务描述与验收标准"},
        "target_paths": {"type": "array", "items": {"type": "string"}, "description": "关注的文件或目录"}
      },
      "required": ["engine", "instruction"]
    }
  },
  {
    "name": "ca_handoff_session",
    "description": "当当前引擎遇到上下文瓶颈、限流或死循环时，主动将当前会话打包并移交给目标引擎继续执行",
    "parameters": {
      "type": "object",
      "properties": {
        "target_engine": {"type": "string", "enum": ["claude", "codex", "opencode", "antigravity"]},
        "reason": {"type": "string", "description": "移交原因与当前进展摘要"}
      },
      "required": ["target_engine"]
    }
  }
]
```

### 2.2 底层运行时：Git Worktree 并发隔离
为了避免多引擎相互调用时修改同一工作区代码导致 git dirty 混乱，所有通过 `ca_delegate_subtask` 或 `ca batch-run` 发起的受委派引擎均在独立 git worktree 中运行：
1. **自动创建临时分支**：`ca/worker-<task-id>` 对应目录 `.git/worktrees/ca-<task-id>`。
2. **Headless 约束执行**：受委派引擎以无头模式（headless / exec）执行，通过管道捕获结构化事件。
3. **结构化合并回传**：执行完毕后生成精简的 git patch 或 diff 统计，并附带执行结论返回给主调用引擎，由主引擎决定是否合入或调整。

---

## 3. 近期功能优化与工程加固

### 3.1 权限姿态治理与安全模式（AUDIT-003）
- **现状问题**：交互式 Codex 默认带有 `--dangerously-bypass-approvals-and-sandbox`，在无 token 回环 API 的环境下存在严重越权风险。
- **优化方案**：
  - 引入全局与每引擎的统一权限策略配置 `approval_mode`（`safe` | `yolo`）。
  - 默认采用 `safe` 模式，严禁无参数默认开启 bypass。
  - 仅当命令行显式带有 `--yolo` 标志或配置文件明确注明 `yolo: true` 时才注入免审批参数。
  - Web 终端状态栏与 CLI 启动横幅中显式提示当前的权限状态（如 `[MODE: SAFE/SANDBOX]`）。

### 3.2 架构去重与引擎单源注册（AUDIT-001 / AUDIT-002）
- **现状问题**：增加一个引擎（如 Antigravity）改动放射到 20+ 个文件；悬空的 Agent Gateway 占用 4,500 行代码且 Web 已退役。
- **优化方案**：
  - 落实单一可信数据源 `core/engine_registry.py`，引擎能力、CLI 候选命令、安装提示、Session 字段一处声明，全局派生。
  - 将 `Agent Gateway` 正式标记为 Experimental 并默认关闭（`CA_AGENT_GATEWAY_ENABLED=0`），不再让双轨架构稀释核心精力。

### 3.3 自然语言定时任务（NL Cron）落地
- **目标**：实现 `docs/superpowers/specs/2026-09-02-natural-language-cron-design.md`。
- **功能特性**：
  - 允许用户使用一句自然语言（如 `"每天凌晨2点拉取最新代码并检查类型安全"`）配置定时任务。
  - 通过调度引擎在后台按计划唤醒 Headless Engine 执行，自动记录 TaskRun 历史并在发生告警时推送通知。

---

## 4. 进阶增值特性：多引擎效能与成本洞察（Engine Benchmarking & ROI Analytics）

现有的 CodeAgent 已具备覆盖 5 个引擎的 Token 与成本收集管道（Analytics Collector）。在此基础上，将其升级为**“开发者决策级效能洞察看板”**：

### 4.1 指标采集维度
1. **任务吞吐与耗时**：跨引擎比较在同等任务规模下的执行秒数与完成效率。
2. **Token 与费用 ROI**：计算单位代码修改量（LOC Modified）所消耗的 Prompt/Completion Token 以及实际法币成本（基于外置动态定价表）。
3. **质量与重试率**：统计不同引擎在面对编译报错/单测失败时的平均自愈重试轮次。

### 4.2 Web 呈现与选型建议
- 在 Web Dashboard 增加「效能雷达图（Efficiency Radar）」与「选型指南推荐」：
  - *“在此代码库中，Antigravity 的代码检索 Token 成本比 Claude 低 40%”*
  - *“在单元测试生成场景下，Codex 的一次通过率达到 85%，性价比较优”*
- 让团队负责人和独立开发者真正清晰感知每一分钱花在了哪里、哪款工具在当前项目中综合产出最高。

---

## 5. 分阶段落地路线图

| 阶段 | 周期 | 核心交付物 | 风险与验收标准 |
|:---|:---|:---|:---|
| **Phase 1: 安全治理与注册表收敛** | 1周 | 1. 提交并固化 Engine Registry（AUDIT-002）<br>2. 实施 Codex 权限安全策略（`--yolo` 门禁，AUDIT-003）<br>3. 默认关闭 Gateway 并补齐单测 | 现有 1,059+ 测试全部通过，Lint 0 错误 |
| **Phase 2: 任务隔离与 NL Cron 落地** | 1-2周 | 1. 为 `ca run` / `ca batch-run` 实现 `--worktree` 隔离执行支持<br>2. 落地自然语言定时任务调度服务（NL Cron） | 多个引擎并发执行不冲突，定时任务按计划自愈 |
| **Phase 3: 跨引擎互调 (ca-mcp)** | 1-2周 | 1. 构建轻量伴生 `ca-mcp` 并在引擎启动时自动挂载<br>2. 实现 `ca_delegate_subtask` 工具并在 Worktree 中收集 Diff<br>3. 实现跨引擎 `ca_handoff_session` 流程 | 跑通端到端：Claude 可主动调用 agy 检索并获取回传结果 |
| **Phase 4: 效能洞察与 ROI 看板** | 1周 | 1. 外置模型定价表与动态更新机制<br>2. 前端展示跨引擎效能、耗时与通过率雷达图看板 | 数据采集无性能回退，生成高可读性洞察报表 |
