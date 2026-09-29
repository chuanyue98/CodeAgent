# 自然语言定时任务（NL Cron）设计

> 日期: 2026-09-02
> 状态: 已确认（用户逐段批准）
> 背景: 借鉴 Hermes Agent 的自然语言 cron（`/cron 每天早上总结 PR`），在 CodeAgent 现有调度器之上补齐「自然语言创建」与「结果站内投递」两个缺口，形成完整闭环。

## 一、目标与非目标

### 目标

1. 用户在 Web UI 用一句自然语言（如「每天早上 9 点总结 PR」）创建定时任务：LLM 解析出 cron 表达式 + 任务定义，回填表单确认后创建。
2. 定时任务运行结算后，按 per-schedule 配置生成站内通知（顶栏铃铛 + 下拉列表），点击可跳转运行详情。

### 非目标（本次不做）

- Telegram / webhook 等外部渠道投递**成功结果**（现有失败 webhook 逻辑保持不动）
- cron 调度守护进程化——调度循环仍挂在 `ca ui` 的 FastAPI lifespan 上，不开 Web UI 无调度
- 自然语言修改/删除现有 schedule
- 浏览器 Notification API 推送、声音提示
- CLI 侧 NL 创建入口（`ca cron add "..."`）

## 二、现状盘点（可复用基建）

| 能力 | 现成实现 |
|---|---|
| cron 解析/校验/下次触发预览 | croniter + `ScheduleService.preview_next_runs` + `GET /api/schedules/preview` |
| 调度循环（到期触发、重叠防护、失败隔离、状态回写） | `core/services/scheduler_loop.py` `tick_once` + `run_task(prevent_overlap=True, schedule_id=...)` |
| 调度记录 CRUD + 持久化 | `core/services/schedule_service.py`（config.json `schedules` 数组，`ConfigService.modify_config` 原子 RMW） |
| LLM headless 一次性执行 | `TaskRunner.run_chat_turn`（`core/services/runner_service.py`） |
| 「AI 产出任务 md 文件」整条链 | `POST /api/tasks/generate`（`_GENERATE_TASK_PROMPT` + `run_chat_turn`），本设计的解析端点直接仿照 |
| 运行跟踪/历史/日志 | RunStore（SQLite `runs.db`，`schedule_id` 列 + 索引）、`TaskService.get_task(name, log_path)` 读日志 |
| 前端页面骨架 | `CronPage.tsx`（表单 + cron 预览 + 列表 + run-now）、`api/schedules.ts` |
| 双语 i18n | `cron.*` / `template.*` key 已就位，en/zh 扁平点号 key |

## 三、总体架构

```
用户输入「每天早上 9 点总结 PR」
        │
        ▼
POST /api/schedules/parse ──► run_chat_turn(engine, _PARSE_SCHEDULE_PROMPT)
        │                       LLM 输出 JSON {cron_expr, 任务四段}
        ▼
回填 CronPage 创建表单（用户可改可确认）
        │
        ▼  点「创建」
POST /api/schedules ──► 物化 tasks/<name>.md + create_schedule（含 notify_on）
        │
        ▼
scheduler_tick_loop 到期 ──► run_task(prevent_overlap, schedule_id)
        │
        ▼
_settle_finished_runs 结算终态 ──► 按 notify_on 写 notifications 表
        │
        ▼
顶栏铃铛（30s 轮询 unread-count）──► 下拉列表 ──► 点击跳转运行详情
```

核心决策：**NL 解析产物物化成任务文件**（方案 A，已选定），调度循环 `tick_once`、`run_task`、`_settle_finished_runs` 主流程不改结构；`schedule` 只加字段，通知走新表。

## 四、组件设计

### 4.1 前端：CronPage NL 输入区

- 位置：CronPage 顶部，「用一句话描述你的定时任务」输入框 + 引擎选择（默认全局默认引擎）+「解析」按钮。
- 点击解析 → 按钮 loading → `POST /api/schedules/parse`；成功后将 `cron_expr`、任务名、四段内容**回填到下方现有创建表单**，并展示 `cron_description` 与 `next_runs` 预览（复用现有 cron 预览组件）。
- 失败：显示错误信息 + `raw_output` 折叠面板（LLM 原始输出）；输入框保留原文。
- 手动表单路径完全不受影响；NL 只是「预填」手段。

### 4.2 后端：解析端点

挂载在现有 `core/web/routers/schedules.py`：

**`POST /api/schedules/parse`**，body：`{ "input": string, "engine": string }`

1. 组装 `_PARSE_SCHEDULE_PROMPT`（双语，模式对齐 `_GENERATE_TASK_PROMPT`），要求 LLM 只输出 JSON：`{cron_expr, name, title, objective, context, instructions, verification}`。
2. 复用 `TaskRunner.run_chat_turn(engine, message)` 执行。
3. 从 JSONL 输出提取结果文本 → 解析 JSON（容错：剥离 markdown 代码围栏）。
4. 后端校验：
   - `cron_expr` 过 `ScheduleService.preview_next_runs`，无效返回 422（附错误说明）；
   - 任务名过 `is_valid_task_name`，无效则自动 slug 化（小写、非法字符转 `-`、截断）；
   - 四段（objective/context/instructions/verification）非空校验，缺失返回 422。
5. 成功响应：

```json
{
  "cron_expr": "0 9 * * *",
  "cron_description": "每天 09:00",
  "next_runs": ["2026-09-03T09:00:00", "..."],   -- 固定 3 次（preview_next_runs 现有默认）
  "task": { "name": "daily-pr-summary", "title": "总结 PR", "objective": "...", "context": "...", "instructions": "...", "verification": "..." },
  "raw_output": "..."
}
```

6. LLM 输出不可解析 / 引擎不可用：返回 `{ "error": string, "raw_output": string|null }` + 422；端点整体超时 120s（模块常量 `PARSE_TIMEOUT_SECONDS`）。
7. 端点**不落盘**——纯解析；创建是显式第二步（幂等、可重试）。

### 4.3 schedule record 扩展

`ScheduleService.create_schedule` / `update_schedule` 字段白名单新增：

- `notify_on`: `"always" | "success" | "failure" | "never"`，默认 `"always"`；非法值拒绝。
- `created_from_input`: string | null——自然语言原文（审计用，手动创建为 null）。

`GET /api/schedules` 响应携带新字段；CronPage 创建表单加 `notify_on` 下拉（四选一，默认 always）。

### 4.4 通知数据层（RunStore 扩展）

`runs.db` 新增 `notifications` 表（建表语句幂等，老库首次访问自动建表 = schema 迁移）：

```sql
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    schedule_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_name TEXT NOT NULL,
    engine TEXT NOT NULL,
    status TEXT NOT NULL,            -- completed | failed | stopped
    title TEXT NOT NULL,
    summary TEXT NOT NULL,           -- 日志末尾截 N 行（N=20，常量）
    read_at REAL                     -- NULL = 未读
);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);
```

RunStore 新增方法：

- `add_notification(schedule_id, task_id, task_name, engine, status, title, summary) -> id`
- `list_notifications(limit=50, unread_only=False) -> list[dict]`（created_at 倒序）
- `count_unread() -> int`
- `mark_read(notification_id)` / `mark_all_read()`
- `prune_notifications(retention_days)`——并入现有 `prune_old_runs` 30 天保留策略（`CA_RUN_RETENTION_DAYS` 同源），保留最近 200 条下限规则同样适用。

### 4.5 通知触发（scheduler_loop 扩展）

`_settle_finished_runs()` 内，run 从 `"started"` 结算为终态后：

1. 读取该 run 的 `schedule_id`（无则跳过）。
2. 查 schedule 的 `notify_on`：
   - `never` → 跳过；
   - `success` → 仅 `completed` 记；
   - `failure` → 仅 `failed` 记；
   - `always` → `completed` / `failed` / `stopped` 均记（`stopped` 是用户主动停止，仅 always 时记）。
3. summary 来源：`TaskService.get_task(name, log_path)` 读日志末段（截 20 行，去除 ANSI 控制符）。
4. 调 `run_store.add_notification(...)`。

现有失败 webhook 通知（`notifier.notify` + `schedule.failed`）**保持不动**。

### 4.6 通知 API + 前端铃铛

**API**（新 router `core/web/routers/notifications.py`）：

- `GET /api/notifications?limit=50&unread_only=false` → 倒序列表
- `GET /api/notifications/unread-count` → `{ "count": int }`
- `POST /api/notifications/{id}/read`
- `POST /api/notifications/read-all`

**前端**：

- 顶栏（全局布局共享处）加铃铛图标：未读数红点徽标。
- `usePolling` 30s 拉 unread-count；点击展开下拉面板：最近 50 条，每条 [状态图标] title · 引擎 · 相对时间 + summary 前 2 行。
- 单条点击 → `mark_read` + 跳转该 run 详情（`GET /api/tasks/runs/{task_id}`，复用现有运行详情展示）；面板底部「全部已读」；空态「暂无通知」。
- i18n：新增 `notifications.*` key，en.ts（类型源）与 zh.ts 同步，`i18n.test.tsx` 保证对齐。

## 五、错误处理

| 场景 | 行为 |
|---|---|
| LLM 输出非 JSON | 422 + `raw_output` 返回，前端折叠面板展示原文 |
| cron 表达式无效 | 422 + croniter 错误说明 |
| 任务名非法 | 自动 slug 化（不报错） |
| 引擎不可用 / 超时（120s） | 422 + 明确错误信息 |
| 通知写表失败 | log warning，不影响结算主流程（best-effort，对齐 notifier 哲学） |
| 旧 runs.db 无 notifications 表 | 首次访问自动建表 |

## 六、测试计划

| 文件 | 覆盖 |
|---|---|
| `tests/test_schedules_router.py` 扩展 | parse 端点：正常解析、LLM 输出不可解析（422 + raw_output）、无效 cron（422）、无效任务名 slug 化、四段缺失（422）、notify_on CRUD |
| `tests/test_schedule_service.py` 扩展 | notify_on 白名单校验（非法值拒绝）、默认 always、created_from_input |
| `tests/test_run_store.py` 扩展 | notifications 表自动迁移、CRUD、未读计数、mark_all_read、prune |
| `tests/test_scheduler_loop.py` 扩展 | 四种 notify_on × 终态组合、stopped 特判、summary 截断与 ANSI 清理、schedule 缺失容错 |
| `web/frontend/src/__tests__/` | CronPage NL 输入→回填流、失败态展示、铃铛轮询/列表/已读交互、i18n key 对齐 |

## 七、文档

- `docs/configuration.md`：修正 schedules 一节过时字段（`name/cron/task` → `id/task_name/cron_expr/...`），补 `notify_on`、`created_from_input`。
- `docs/commands.md`：无新增 CLI，不改。

## 八、涉及文件清单

**后端**：
- `core/web/routers/schedules.py`（+parse 端点）
- `core/web/routers/notifications.py`（新建）
- `core/web/server.py`（挂载 notifications router）
- `core/services/schedule_service.py`（字段白名单 + notify_on 校验）
- `core/services/run_store.py`（notifications 表 + 方法 + prune）
- `core/services/scheduler_loop.py`（结算后写通知）
- `core/i18n.py`（若后端有用户可见文案）

**前端**：
- `web/frontend/src/components/CronPage.tsx`（NL 输入区 + notify_on 表单项）
- `web/frontend/src/api/schedules.ts`（parseSchedule）
- `web/frontend/src/api/notifications.ts`（新建）
- `web/frontend/src/components/`（铃铛组件，挂到全局布局）
- `web/frontend/src/i18n/locales/en.ts` / `zh.ts`

**测试**：上述第五节表格所列文件。

**文档**：`docs/configuration.md`。
