# 全系统视觉与工作流闭环（Cohesive Studio）全面重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全面优化 CodeAgent 首页（仪表盘与自动化微件）、会话活动页（长消息类型过滤器）、定时任务页（宽屏比例栅格与通知策略透视）及系统设置页（工作区输入框与资源分组直达），形成连贯一致的开发控制台体验。

**Architecture:**
- **HomePage**: 引入自动化运行监控微件与核心三合一快捷工作流条；
- **SessionDetailPanel**: 增加长对话消息类型过滤工具条（全部/用户指令/模型回复/工具调用/思考过程）；
- **CronPage**: 升级为 `xl:grid-cols-12`（5:7）自适应栅格，并在任务卡片展示通知策略与倒计时；
- **ConfigHub**: 现代化工作区输入控件，增加分组一键跳转至资源库。

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Lucide Icons.

## Global Constraints

- 严禁引入任何新的 npm 依赖（使用现有的 `react-markdown`、`lucide-react`、Tailwind CSS）。
- 所有 Python 检验通过 `uv run`（严禁使用 pip/venv）。
- 中英双语词条必须在 `web/frontend/src/i18n/locales/en.ts` 与 `zh.ts` 保持键和占位符严格一一对应。
- 交付前必须通过 `bun run test`、`bun run lint`、`bun run build`、`uv run pytest`、`uv run ruff check .`、`uv run mypy core`。

---

### Task 1: 辅助函数与 i18n 全面扩充

**Files:**
- Modify: `web/frontend/src/utils/workspaceFormat.ts`
- Test: `web/frontend/src/__tests__/workspaceFormat.test.ts`
- Modify: `web/frontend/src/i18n/locales/en.ts`
- Modify: `web/frontend/src/i18n/locales/zh.ts`
- Test: `web/frontend/src/__tests__/i18n.test.tsx`

**Interfaces:**
- Produces:
  ```ts
  export function formatRelativeCountdown(targetTimestampSec: number, language?: string): string;
  ```
- Consumes: 新增 i18n 键（会话消息过滤、首页自动化微件、设置分组直达）。

- [ ] **Step 1: 在 `workspaceFormat.test.ts` 中添加 `formatRelativeCountdown` 单元测试**
- [ ] **Step 2: 运行测试并验证失败**
- [ ] **Step 3: 实现 `formatRelativeCountdown` 函数**
- [ ] **Step 4: 扩充 `en.ts` 与 `zh.ts` 对应双语词条**
- [ ] **Step 5: 验证测试通过**
- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/utils/workspaceFormat.ts web/frontend/src/__tests__/workspaceFormat.test.ts web/frontend/src/i18n/locales/en.ts web/frontend/src/i18n/locales/zh.ts
git commit -m "feat(i18n): add cohesive studio full app translation keys and countdown formatter"
```

---

### Task 2: 会话详情抽屉消息类型过滤器（SessionDetailPanel）

**Files:**
- Modify: `web/frontend/src/components/SessionDetailPanel.tsx`
- Test: `web/frontend/src/__tests__/SessionDetailPanel.test.tsx`

**Interfaces:**
- Filter types: `'all' | 'user' | 'assistant' | 'tool' | 'thinking'`
- Filters messages rendered in the panel list without altering original session events.

- [ ] **Step 1: 编写/扩充 `SessionDetailPanel.test.tsx` 测试消息类型过滤**
- [ ] **Step 2: 运行测试验证失败**
- [ ] **Step 3: 在 `SessionDetailPanel.tsx` 中实现过滤器状态与过滤逻辑**
- [ ] **Step 4: 运行测试验证通过**
- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/components/SessionDetailPanel.tsx web/frontend/src/__tests__/SessionDetailPanel.test.tsx
git commit -m "feat(activity): add message type filter bar to SessionDetailPanel"
```

---

### Task 3: 首页自动化状态微件与快捷工作流（HomePage）

**Files:**
- Modify: `web/frontend/src/pages/HomePage.tsx`
- Test: `web/frontend/src/__tests__/HomePage.test.tsx`

**Interfaces:**
- Consumes: `/api/tasks/runs`, `/api/schedules`
- Adds:
  - Automation Widget card with active runs count, completed count, next schedule.
  - Quick action workflow buttons (Agent Terminal, New Task, New Schedule).
  - Refined system metrics tone.

- [ ] **Step 1: 编写 `HomePage.test.tsx` 针对自动化微件与快捷入口的测试**
- [ ] **Step 2: 运行测试验证失败**
- [ ] **Step 3: 在 `HomePage.tsx` 中集成自动化微件与操作条**
- [ ] **Step 4: 运行测试验证通过**
- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/pages/HomePage.tsx web/frontend/src/__tests__/HomePage.test.tsx
git commit -m "feat(home): add automation monitor widget and quick actions to HomePage"
```

---

### Task 4: 定时任务宽屏栅格与通知策略透视（CronPage）

**Files:**
- Modify: `web/frontend/src/components/CronPage.tsx`
- Test: `web/frontend/src/__tests__/CronPage.test.tsx`

**Interfaces:**
- Layout upgrade: `grid grid-cols-1 xl:grid-cols-12 gap-6` (Form 5 cols, Schedules 7 cols).
- Schedule card displays `notify_on` badge and relative countdown for next run.

- [ ] **Step 1: 检查现有 `CronPage.test.tsx`**
- [ ] **Step 2: 修改 `CronPage.tsx` 布局与卡片元信息**
- [ ] **Step 3: 运行测试验证通过**
- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/components/CronPage.tsx web/frontend/src/__tests__/CronPage.test.tsx
git commit -m "feat(schedules): improve CronPage desktop grid and add notification badges"
```

---

### Task 5: 设置配置页工作区输入框与分组直达（ConfigHub）

**Files:**
- Modify: `web/frontend/src/components/ConfigHub.tsx`
- Test: `web/frontend/src/__tests__/ConfigHub.test.tsx`

**Interfaces:**
- Workspace input: modern bordered card with folder icon and check/warning indicator.
- Group definition cards: "View Resources" button linking to `/settings/resources?group=${name}`.

- [ ] **Step 1: 编写/更新 `ConfigHub.test.tsx` 验证资源跳转与工作区输入**
- [ ] **Step 2: 修改 `ConfigHub.tsx`**
- [ ] **Step 3: 运行测试验证通过**
- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/components/ConfigHub.tsx web/frontend/src/__tests__/ConfigHub.test.tsx
git commit -m "feat(config): modernize workspace input and add direct resource navigation"
```

---

### Task 6: 全量质量回归与生产构建

- [ ] **Step 1: 前端 Lint 检查** (`bun run --cwd web/frontend lint`)
- [ ] **Step 2: 前端全量单测** (`bun run --cwd web/frontend test`)
- [ ] **Step 3: 前端生产构建** (`bun run --cwd web/frontend build`)
- [ ] **Step 4: Python 后端 Lint 与类型检查** (`uv run ruff check .` && `uv run mypy core`)
- [ ] **Step 5: Python 后端全量测试** (`uv run pytest`)
- [ ] **Step 6: 重启后台 UI 服务并验证实机效果**
