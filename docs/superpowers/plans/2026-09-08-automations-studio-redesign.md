# 自动化工作台（Automations Studio）UI/UX 全面重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 CodeAgent 自动化（Automations）模块（任务详情、任务列表、日志查看器）彻底升级为现代化的 Studio 工作台体验，解决宽屏空白过大、文字截断、裸 Markdown pre 渲染、日志与蓝图割裂等体验问题。

**Architecture:**
- **TaskDetail**: 宽屏自适应双栏（70% 主工作区 + 30% 检查面板），顶栏重组为语义化工具条；主工作区采用常驻选项卡（蓝图 Blueprint、实时终端 Logs、代码变更 Changes、运行历史 History），蓝图使用结构化四段式卡片与富文本 Markdown 渲染。
- **TaskList**: 解除 `max-w-4xl` 窄屏限制，采用响应式多列网格，增强卡片元数据表现力。
- **LogViewer**: 增加行内关键词过滤、自动滚屏切换开关、复制全部日志与全屏查看模式。
- **i18n & 格式化**: 全面支持中英双语，统一工作区显示与路径 tooltip。

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Lucide Icons, `react-markdown`.

## Global Constraints

- 严禁引入任何新的 npm 依赖（使用现有的 `react-markdown`、`lucide-react`、Tailwind CSS）。
- 所有 Python 检验通过 `uv run`（严禁使用 pip/venv）。
- 中英双语词条必须在 `web/frontend/src/i18n/locales/en.ts` 与 `zh.ts` 保持键和占位符严格一致。
- 交付前必须通过 `bun run test`、`bun run lint`、`bun run build`、`uv run pytest`、`uv run ruff check .`、`uv run mypy core`。

---

### Task 1: 工作区显示辅助函数与 i18n 字典扩充

**Files:**
- Modify: `web/frontend/src/utils/workspaceFormat.ts`
- Test: `web/frontend/src/__tests__/workspaceFormat.test.ts`
- Modify: `web/frontend/src/i18n/locales/en.ts`
- Modify: `web/frontend/src/i18n/locales/zh.ts`
- Test: `web/frontend/src/__tests__/i18n.test.tsx`

**Interfaces:**
- Produces:
  ```ts
  export function formatWorkspaceLabel(path: string, group?: string): string;
  ```
- Consumes: i18n 键集，新增 `taskDetail.tabBlueprint`, `taskDetail.tabLogs`, `taskDetail.tabChanges`, `taskDetail.tabHistory`, `taskDetail.scheduleThisTask`, `taskDetail.objective`, `taskDetail.context`, `taskDetail.instructions`, `taskDetail.verification`, `logs.searchPlaceholder`, `logs.copyAll`, `logs.copied`, `logs.autoScroll`, `logs.fullscreen`

- [ ] **Step 1: 在 `workspaceFormat.test.ts` 中添加 `formatWorkspaceLabel` 单元测试**

```typescript
import { describe, expect, test } from 'vitest';
import { formatWorkspaceLabel } from '../utils/workspaceFormat';

describe('formatWorkspaceLabel', () => {
  test('formats workspace path with basename and optional group', () => {
    expect(formatWorkspaceLabel('/home/cy/github/chuanyue98/CodeAgent', 'codeagent')).toBe('CodeAgent (codeagent)');
    expect(formatWorkspaceLabel('/home/cy/github/chuanyue98/CodeAgent')).toBe('CodeAgent');
    expect(formatWorkspaceLabel('/')).toBe('/');
  });
});
```

- [ ] **Step 2: 运行测试并验证失败**

Run: `bun run --cwd web/frontend test src/__tests__/workspaceFormat.test.ts`
Expected: FAIL with "formatWorkspaceLabel is not exported"

- [ ] **Step 3: 在 `workspaceFormat.ts` 中实现 `formatWorkspaceLabel`**

```typescript
export function formatWorkspaceLabel(path: string, group?: string): string {
  if (!path) return '';
  const trimmed = path.replace(/[/\\]+$/, '');
  const basename = trimmed.split(/[/\\]/).pop() || path;
  if (group && group !== 'common') {
    return `${basename} (${group})`;
  }
  return basename;
}
```

- [ ] **Step 4: 扩充 `en.ts` 与 `zh.ts` 对应词条**

添加 Studio 选项卡、四段蓝图、日志增强等相关双语键。

- [ ] **Step 5: 运行 i18n 与格式化测试验证通过**

Run: `bun run --cwd web/frontend test src/__tests__/workspaceFormat.test.ts src/__tests__/i18n.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/utils/workspaceFormat.ts web/frontend/src/__tests__/workspaceFormat.test.ts web/frontend/src/i18n/locales/en.ts web/frontend/src/i18n/locales/zh.ts
git commit -m "feat(i18n): add automations studio translation keys and workspace formatter"
```

---

### Task 2: 任务蓝图结构化渲染组件（TaskBlueprintView）

**Files:**
- Create: `web/frontend/src/components/TaskDashboard/TaskBlueprintView.tsx`
- Test: `web/frontend/src/__tests__/TaskBlueprintView.test.tsx`

**Interfaces:**
- Produces:
  ```tsx
  export interface TaskBlueprintViewProps {
    content?: string;
    title: string;
  }
  export default function TaskBlueprintView(props: TaskBlueprintViewProps): ReactElement;
  ```
- Consumes: `MarkdownMessage` from `../MarkdownMessage`

- [ ] **Step 1: 编写 `TaskBlueprintView.test.tsx` 验证四段解析与通用 Markdown 渲染**

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import TaskBlueprintView from '../components/TaskDashboard/TaskBlueprintView';

describe('TaskBlueprintView', () => {
  test('parses and renders four-section blueprint with cards', () => {
    const content = `
# Sample Task
## Objective (目标)
Do some cleanup.
## Context (背景)
Technical debt.
## Instructions (指令)
1. Step one.
## Verification (验证)
Run tests.
`;
    render(<TaskBlueprintView content={content} title="Sample Task" />);
    expect(screen.getByText(/Do some cleanup/)).toBeVisible();
    expect(screen.getByText(/Technical debt/)).toBeVisible();
    expect(screen.getByText(/Step one/)).toBeVisible();
    expect(screen.getByText(/Run tests/)).toBeVisible();
  });
});
```

- [ ] **Step 2: 运行测试并验证失败**

Run: `bun run --cwd web/frontend test src/__tests__/TaskBlueprintView.test.tsx`
Expected: FAIL (component doesn't exist yet)

- [ ] **Step 3: 实现 `TaskBlueprintView.tsx`**

实现对四段式蓝图（Objective / Context / Instructions / Verification）的智能切分，并在每段使用语义卡片呈现；对于非标准四段式的 Markdown，使用 `MarkdownMessage` 完整保真渲染。

- [ ] **Step 4: 运行测试并验证通过**

Run: `bun run --cwd web/frontend test src/__tests__/TaskBlueprintView.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/components/TaskDashboard/TaskBlueprintView.tsx web/frontend/src/__tests__/TaskBlueprintView.test.tsx
git commit -m "feat(task-dashboard): add structured TaskBlueprintView component"
```

---

### Task 3: 任务详情 Studio 工作台布局重构（TaskDetail）

**Files:**
- Modify: `web/frontend/src/components/TaskDashboard/TaskDetail.tsx`
- Test: `web/frontend/src/__tests__/TaskDashboard.test.tsx`

**Interfaces:**
- Consumes: `TaskBlueprintView`, `LogViewer`, `RunChanges`, `formatWorkspaceLabel`
- Modifies UI layout:
  - 顶栏：面包屑导航、工作区完整路径 tooltip、引擎切换与突出运行/停止主按钮、分组更多操作；
  - 主体：全宽自适应双栏（70% 主工作区 Tabs + 30% 侧边检查器）；
  - 主 Tabs：`Blueprint`、`Terminal Logs`、`Changes`、`Run History`；
  - 检查器：最近运行卡片、关联技能紧凑列表、一键转定时任务入口。

- [ ] **Step 1: 检查现有 `TaskDashboard.test.tsx` 保证基线测试清晰**

Run: `bun run --cwd web/frontend test src/__tests__/TaskDashboard.test.tsx`
Expected: PASS

- [ ] **Step 2: 重构 `TaskDetail.tsx` 页面布局**

1. 移除 `max-w-4xl mx-auto`，采用 `w-full space-y-5`。
2. 顶栏操作区：重构环境选择栏，使用 `formatWorkspaceLabel` 并添加 `title={workspace}` 悬浮提示。
3. 选项卡机制：将 `logTab` 升级为 `activeTab: 'blueprint' | 'logs' | 'changes' | 'history'`。
4. 无论任务是否处于运行或有日志，蓝图和日志永远常驻可通过 Tab 自由切换。
5. 侧边栏：紧凑折叠技能卡片与快速设为定时任务快捷按钮。

- [ ] **Step 3: 运行 `TaskDashboard.test.tsx` 验证现有交互与新布局兼容**

Run: `bun run --cwd web/frontend test src/__tests__/TaskDashboard.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/components/TaskDashboard/TaskDetail.tsx
git commit -m "feat(task-dashboard): refactor TaskDetail into wide-screen studio layout"
```

---

### Task 4: 任务列表（TaskList）宽屏响应式网格优化

**Files:**
- Modify: `web/frontend/src/components/TaskDashboard/TaskList.tsx`
- Test: `web/frontend/src/__tests__/TaskList.test.tsx`

**Interfaces:**
- Consumes: Task list, active runs, filters
- Layout changes:
  - 解除 `max-w-4xl`；
  - 任务列表采用 `grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4` 响应式流式布局；
  - 卡片增强：显示清晰的引擎标签、运行耗时、状态小圆点与快捷详情箭头。

- [ ] **Step 1: 运行现有的 `TaskList.test.tsx` 验证基线**

Run: `bun run --cwd web/frontend test src/__tests__/TaskList.test.tsx`
Expected: PASS

- [ ] **Step 2: 修改 `TaskList.tsx` 为响应式网格**

将狭窄列表容器替换为响应式网格排布，优化间距与状态徽标。

- [ ] **Step 3: 运行 `TaskList.test.tsx` 验证通过**

Run: `bun run --cwd web/frontend test src/__tests__/TaskList.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/components/TaskDashboard/TaskList.tsx
git commit -m "feat(task-dashboard): convert TaskList to responsive widescreen grid"
```

---

### Task 5: 运行日志查看器（LogViewer）体验增强

**Files:**
- Modify: `web/frontend/src/components/LogViewer.tsx`
- Test: `web/frontend/src/__tests__/LogViewer.test.tsx`

**Interfaces:**
- Consumes: log stream, log file content
- Enhancements:
  - 顶部控制条：关键词快速过滤输入框；
  - 自动滚动开关（Auto-scroll toggle）；
  - 一键复制全部日志按钮（Copy all logs）；
  - 全屏终端模式（Fullscreen toggle）。

- [ ] **Step 1: 编写 `LogViewer.test.tsx` 测试新增的控制条功能**

测试过滤关键词、复制和自动滚动切换交互。

- [ ] **Step 2: 运行测试验证失败**

Run: `bun run --cwd web/frontend test src/__tests__/LogViewer.test.tsx`
Expected: FAIL

- [ ] **Step 3: 在 `LogViewer.tsx` 中实现控制条与过滤**

- [ ] **Step 4: 运行测试验证通过**

Run: `bun run --cwd web/frontend test src/__tests__/LogViewer.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/components/LogViewer.tsx web/frontend/src/__tests__/LogViewer.test.tsx
git commit -m "feat(logs): add search filter, auto-scroll toggle, and copy tools to LogViewer"
```

---

### Task 6: 全量质量回归与生产构建

**Files:**
- 全局验证

- [ ] **Step 1: 前端 Lint 检查**
Run: `bun run --cwd web/frontend lint`
Expected: 0 errors, 0 warnings

- [ ] **Step 2: 前端全量单测**
Run: `bun run --cwd web/frontend test`
Expected: ALL PASS

- [ ] **Step 3: 前端生产构建**
Run: `bun run --cwd web/frontend build`
Expected: 0 errors, output to `dist/`

- [ ] **Step 4: Python 后端 Lint 与类型检查**
Run: `uv run ruff check .` && `uv run mypy core`
Expected: All checks passed, 0 errors

- [ ] **Step 5: Python 后端全量测试**
Run: `uv run pytest`
Expected: 1097+ passed

- [ ] **Step 6: 重启后台 UI 服务并验证真实运行效果**
Run: 重启 UI 服务并检查日志无报错。
