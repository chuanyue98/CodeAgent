# 多 Agent 协作编排 — 调研与设计

> 调研日期: 2026-07-11
> 目的: 评估 oh-my-openagent / oh-my-pi / OpenHarness 的多 agent 实现，结合 CodeAgent 自身约束（包装官方 CLI，而非直连 API），设计一版可落地的多 agent 协调方案。

---

## 一、核心约束

CodeAgent 的引擎层是对**官方 CLI 工具**（`claude`, `codex`, `gemini`, `opencode`）的封装（`ca_launcher.py {engine} -t {task} -y`），不是直连 LLM API。这与调研的三个项目有本质区别：

- 如果是直连 API，自己就是 agent loop 的实现者，"多 agent" 只是进程内并发调用 —— 一个统一实现就够了。
- 包装官方 CLI 意味着每个引擎是**黑盒、一次性调用、跑完退出**，中途没有通用的"塞消息进去"的通道。CodeAgent 现有的 hooks（`before_tool`/`after_tool`，见 `hooks/base/*/metadata.json`）作用域也只到单次 run 内部，够不到跨 session 通信。

## 二、三个项目的实现机制

### oh-my-openagent (`packages/team-core`)
- tmux pane 承载每个 team member 进程，可选 git worktree 隔离（`team-worktree/manager.ts`）
- **Mailbox**：JSON 消息文件 + reservation/ack（`team-mailbox/inbox.ts`）
- **共享任务表**：文件锁 claim + 5 分钟过期自动回收（`team-tasklist/claim.ts`, `CLAIM_STALE_AFTER_MS`）
- **运行中消息投递**：靠 `omo-opencode/src/hooks/team-mailbox-injector` —— 一个挂在 **OpenCode 插件系统**上的 hook。`omo-codex` 对应能力明显弱（只有 skill 级脚本），说明这套东西是按供应商单独适配的，不是通用方案。

### oh-my-pi
- 内建 `task` 工具：进程内 child session，`Semaphore` 限流，`AsyncJobManager` 管理 `running/idle/parked/aborted` 状态。**要求自己是 agent loop 的实现者**，对 CodeAgent 不适用。
- `swarm-extension`：YAML 声明 DAG（`waits_for`/`reports_to`），拓扑排序分 wave，wave 内并行、wave 间顺序；agent 间靠**共享 workspace 目录**协调，不靠消息传递；状态持久化到 `.swarm_<name>/state/pipeline.json`。**这一层是"任务边界"协调，不需要碰任何单一 CLI 的内部机制** —— 对 CodeAgent 最具可移植性。

### OpenHarness
- 统一 `TeammateExecutor` 接口，三种可插拔 backend：`in_process`（asyncio + contextvars，同样要求自己是 loop）、`subprocess`（复用 `BackgroundTaskManager`，走 stdin/stdout，但需要 CLI 支持持续喂输入）、tmux/iTerm2 pane。自动探测环境（`$TMUX`、`it2` CLI）选后端。

## 三、结论：CodeAgent 能抄什么

跨四个引擎通用、不需要碰任何单一 CLI 内部插件 API 的，只有**任务边界协调**这一种模式：

1. 每个 agent = 一次完整的、一次性的官方 CLI 调用（已经是 `TaskRunner.run_task` 的形态）
2. 多个 agent 之间靠 **DAG 依赖 + wave 排序**（抄 oh-my-pi `swarm-extension`）
3. 需要防止并发抢同一任务时，靠**文件锁 claim + 过期回收**（抄 oh-my-openagent `team-tasklist`）
4. Agent 间"通信"就是读写共享工作区里的文件（比如上一阶段把方案写成文档，下一阶段的 prompt 里让它去读）—— 不需要任何新 IPC

明确不抄的，及原因：
- **运行中消息注入** —— 强绑定单一 CLI 插件系统（OpenCode 独有），四个引擎里只有一个能做，不通用。
- **进程内 subagent（oh-my-pi task 工具 / OpenHarness in_process）** —— 要求自己是 agent loop，CodeAgent 摸不到官方 CLI 内部。
- **tmux 可视化** —— 纯 UX 选项，CodeAgent 已有 Web Dashboard 覆盖"看进度"的需求，不需要再引入终端复用器依赖。
- **git worktree 隔离** —— 有价值但不是 v1 必需，见下方"已知限制"。

## 四、设计：Crew（DAG/Wave）编排

### 4.1 Crew Spec

新增一种资源类型，与现有 `tasks/*.md`（单任务）平行，描述"多个任务如何组合"：

```yaml
# tasks/crews/refactor-auth.crew.yaml
crew:
  name: refactor-auth
  members:
    plan:
      task: architect-planning   # 复用现有 tasks/*.md 的任务名
      engine: claude
      group: codeagent
    impl-backend:
      task: implement-backend
      engine: codex
      group: work
      waits_for: [plan]
    impl-frontend:
      task: implement-frontend
      engine: opencode
      group: web
      waits_for: [plan]
    review:
      task: code-review
      engine: gemini
      waits_for: [impl-backend, impl-frontend]
```

`task`/`engine`/`group` 字段直接对应 `TaskRunner.run_task(task_name, engine, group)` 现有参数，不需要改动 `TaskRunner` 本身。

### 4.2 新增组件

| 组件 | 职责 | 备注 |
|------|------|------|
| `core/services/crew_service.py` | 解析 crew spec，用 `waits_for` 建 DAG，拓扑排序分 wave，检测环 | 纯逻辑，不碰进程，可独立测试 |
| `core/services/crew_runner.py` | 按 wave 顺序调用现有 `TaskRunner.run_task`，wave 内成员并行；一个 wave 全部 `completed`/`failed` 后才推进下一个 wave；状态落盘到 `.ca_task_logs/crews/<crew_run_id>/state.json`（现在 `active_runs` 只在内存里，服务重启就丢，这个顺便补上持久化） | 复用 `TaskRunner`，不重复造子进程管理 |
| `core/web/routers/crews.py` | `POST /api/crews/{name}/run`、`GET /api/crews/runs`、`GET /api/crews/runs/{id}`（含每个 member 的 `TaskRunStatus` + 日志）、`POST /api/crews/runs/{id}/stop` | 复用现有 `tasks/runs/*` 的响应结构 |
| 前端：`CrewDashboard.tsx` + `/crews` 路由 | 按 wave 分列渲染，每个节点复用 `TaskDashboard` 现有的 run-card，沿用同样的 2s 轮询模式（`pollActiveRun` 的思路推广到多 run） | — |

失败策略：默认整个 crew 遇到成员失败即停（后续 wave 标记 `blocked`），先不做 `on_failure: continue` 之类的可配置项，避免 v1 过度设计。

### 4.3 已知限制（有意不在 v1 解决）

- **同一 wave 内多个成员写同一份代码可能冲突**（比如 `impl-backend`/`impl-frontend` 都跑在同一份工作区）。oh-my-openagent/oh-my-pi 都用 git worktree 隔离解决。v1 先靠 crew 作者自己保证同 wave 成员改动路径不重叠，v2 再考虑抄 `team-worktree/manager.ts` 加 `worktree: true` 可选项。
- **work-stealing 任务池**（N 个 worker 抢一堆同类任务，而不是固定 DAG）目前没做，真有需求再加文件锁 claim（`team-tasklist/claim.ts` 的思路，`CLAIM_STALE_AFTER_S` 过期回收防死锁）。

### 4.4 落地顺序建议

1. `crew_service.py`：spec 解析 + 拓扑排序 + 环检测（纯逻辑，先写测试）
2. `crew_runner.py`：包一层 `TaskRunner`，加状态落盘
3. `crews` 路由，接入 `server.py`
4. 前端 `CrewDashboard` + 导航项
5. （fast-follow）git worktree 隔离
6. （按需）文件锁 task claim，用于任务池模式
