# 2026-07-11 Web UI: SSE 日志流 + SessionsPage + System Health 面板设计

## 目标

基于现有 CodeAgent Web UI，新增三组功能：

1. SSE 化日志流 — 实时 tail task log
2. SessionsPage — 基于 analytics 数据的深度会话浏览器
3. System Health / Logs 面板 — 底部状态栏 + `/system` 页面

---

## 一、SSE 化日志流

### 后端 (`core/web/routers/logs.py`)

新增 3 个 endpoint：

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/logs/files` | 列出 `.ca_task_logs/` 下所有 log 文件（文件名、大小、最后修改时间） |
| `GET` | `/api/logs/{task_id}` | 读取完整 log 文件内容（首次加载用） |
| `GET` | `/api/logs/{task_id}/stream` | **SSE 流式** — `StreamingResponse` + async generator 实时 tail 文件 |

实现方式：
- 文件读取时用 `collections.deque(maxlen=1000)` 做有限缓冲
- SSE async generator 每 300ms 检查一次新内容，有变化就发 `data: {...}\n\n`
- 文件不存在时返回 404

### 前端 (`web/frontend/src/api/logs.ts` + `components/LogViewer.tsx`)

- `useLogStream(taskId)` hook — 基于原生 `EventSource`，自动重连
- `LogViewer` 组件 — 左侧文件列表，右侧滚动日志区，支持自动滚底/暂停

与现有 TaskDashboard 的关系：TaskDashboard 的轮询改为复用 `LogViewer` 组件。

---

## 二、SessionsPage

### 后端

已有 `GET /api/analytics/sessions`，数据已包含 `modelBreakdowns`。需做的：

- 在 `SessionUsage` TypeScript 接口中补上 `modelBreakdowns` 字段
- 如需查看完整消息线程，新增 `GET /api/analytics/sessions/{session_id}/messages`（可选，待确认）

### 前端 (`web/frontend/src/components/SessionsPage.tsx`)

- 路由：`/sessions`
- 布局：左侧筛选栏（按 engine 多选、日期范围、搜索项目路径），右侧会话卡片列表
- 会话卡片：可展开，显示 modelBreakdowns 明细 + 费用明细
- 排序：按 lastActivity 降序（默认）

与现有 Analytics.Sessions tab 的关系：Analytics tab 保持现状（概览用），SessionsPage 是深度浏览工具。

---

## 三、System Health / Logs 面板

### 后端 (`core/web/routers/system.py`)

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/system/health` | 暴露 `core/doctor.py` 的所有检查结果（JSON） |
| `GET` | `/api/system/metrics` | 轻量系统指标：CPU、内存、磁盘、运行时间、历史文件大小 |

实现方式：
- `doctor.py` 不动，在 router 中 import 并调用 `run_doctor(fix=False)` 转为 JSON
- `metrics` 用 `psutil`（新增依赖）

### 前端

两种形态都做：

1. **底部固定栏**（fixed footer bar）— 始终可见，显示 CPU/内存/磁盘/运行时间/日志文件数量，颜色阈值（绿/黄/红），点击展开详情
2. **独立页面 `/system`** — 展开显示完整 doctor 检查结果 + 集中 Log 查看器（复用 LogViewer）

---

## 总体目录结构

```
core/web/routers/
├── analytics.py   (已有，稍改 — SessionUsage 加 modelBreakdowns)
├── logs.py        (新增 ①)
├── system.py      (新增 ③)
└── ...

web/frontend/src/
├── api/
│   ├── analytics.ts  (补 modelBreakdowns)
│   ├── logs.ts       (新增 ①)
│   └── system.ts     (新增 ③)
├── components/
│   ├── LogViewer.tsx     (新增 ①，③ 复用)
│   ├── SessionsPage.tsx  (新增 ②)
│   └── SystemPanel.tsx   (新增 ③ — footer bar + /system page)
└── App.tsx               (加 /sessions 和 /system 路由)
```

---

## 依赖变化

| 层面 | 变化 |
|------|------|
| 后端 | 新增 `psutil`（system metrics） |
| 前端 | 无新增依赖，原生 `EventSource` + 已有 `lucide-react` |

---

## 实施顺序

按需求：① → ② → ③

- ① 是基础设施，③ 的 LogViewer 复用
- ② 独立，不依赖 ①/③