# Hermes Web UI 参考文档

> 调研日期: 2026-07-11
> 目的: 为 CodeAgent Web UI 改进提供参考

---

## 一、Hermes Agent 官方 Web UI

**仓库**: `NousResearch/hermes-agent/web/`
**Stars**: 213k
**许可**: MIT

### 技术栈

| 类别 | 选型 |
|------|------|
| 构建 | Vite 8 |
| 框架 | React 19 + TypeScript 6 |
| 样式 | Tailwind CSS v4 + 内部 DS `@nous-research/ui` (0.18.2) |
| 路由 | react-router-dom v7.17 |
| 图表 | `@observablehq/plot` (0.6.17) |
| 图标 | lucide-react (0.577) |
| 动画 | motion (12.38) + gsap (3.15) |
| 终端 | `@xterm/xterm` (6.0) + addon-fit/unicode11/web-links/webgl |
| 3D | `@react-three/fiber` (9.6) + three (0.180) |
| 调试面板 | leva (0.10) |
| CSS 工具 | class-variance-authority, clsx, tailwind-merge |
| 测试 | vitest (4.1), playwright (e2e) |
| 其他 | qrcode, unicode-animations |

### 页面清单 (20 个)

| 页面 | 文件 | 功能说明 |
|------|------|---------|
| StatusPage | `pages/StatusPage.tsx` | Agent 状态总览，活跃/近期会话 |
| ChatPage | `pages/ChatPage.tsx` | 浏览器内对话，SSE 流式输出，tool call 渲染 |
| SessionsPage | `pages/SessionsPage.tsx` | 会话历史浏览，按日期/模型/Token/费用排序 |
| AnalyticsPage | `pages/AnalyticsPage.tsx` | 使用分析仪表盘 |
| ConfigPage | `pages/ConfigPage.tsx` | 动态配置编辑器（从后端读取 schema） |
| EnvPage | `pages/EnvPage.tsx` | API Key 管理（保存/清除） |
| CronPage | `pages/CronPage.tsx` | 定时任务调度，cron 表达式编辑 |
| SkillsPage | `pages/SkillsPage.tsx` | 技能浏览/安装/卸载 |
| PluginsPage | `pages/PluginsPage.tsx` | 插件管理 |
| McpPage | `pages/McpPage.tsx` | MCP 服务器管理 |
| ModelsPage | `pages/ModelsPage.tsx` | 模型管理/切换 |
| ProfilesPage | `pages/ProfilesPage.tsx` | 身份/Profile 管理 |
| ProfileBuilderPage | `pages/ProfileBuilderPage.tsx` | 身份构建向导 |
| ChannelsPage | `pages/ChannelsPage.tsx` | 消息渠道配置（Telegram/Discord/Slack 等） |
| FilesPage | `pages/FilesPage.tsx` | 文件浏览/管理 |
| LogsPage | `pages/LogsPage.tsx` | 实时日志查看 |
| SystemPage | `pages/SystemPage.tsx` | 系统健康（CPU/内存/磁盘/运行时间） |
| WebhooksPage | `pages/WebhooksPage.tsx` | Webhook 管理 |
| DocsPage | `pages/DocsPage.tsx` | 内嵌文档 |
| PairingPage | `pages/PairingPage.tsx` | 设备配对（Telegram DM 等） |

### 目录结构

```
web/src/
├── components/ui/       # 可复用 UI 基元 (Card, Badge, Button, Input 等)
├── contexts/            # React Context
├── hooks/               # 自定义 hooks
├── i18n/                # 国际化
├── lib/
│   ├── api.ts           # API 客户端 — 类型化 fetch 包装
│   └── utils.ts         # cn() Tailwind class 合并工具
├── pages/               # 20 个页面组件
├── plugins/             # 插件系统
├── themes/              # 主题系统
├── App.tsx              # 主布局和导航
├── main.tsx             # React 入口
└── index.css            # Tailwind 导入和主题变量
```

### 设计和 UX 规范

1. **字体层级**
   - Brand chrome: `font-mondwest text-display` — 侧边栏导航、Card 标题
   - Themed body: `font-mondwest normal-case` — Card 内容、会话行、分析表格
   - Page chrome: `font-expanded` — 页面标题
   - 技术内容: `font-mono-ui` — 模型名、环境变量、YAML

2. **颜色语义化**
   - `text-text-primary` — 默认正文
   - `text-text-secondary` — 副标题、元数据
   - `text-text-tertiary` — 小标签、计数、脚注
   - `text-text-disabled` — 禁用状态
   - `text-text-on-accent` — 强调色背景上的文字

3. **最小字号**: `text-xs` (12px)，禁止使用 `text-[9px]` `text-[10px]` `text-[11px]`
4. **透明度**: 文字透明度不低于 0.7
5. **大写**: 通过 `text-display` 工具类控制，非全局

### 启动方式

```bash
# 1. 启动后端 API 服务器
cd ../
python -m hermes_cli.main web --no-open

# 2. 启动 Vite 开发服务器 (HMR + API 代理)
cd web/
npm install
npm run dev

# 生产: hermes dashboard (端口 9119，服务内置构建包)
```

### 构建输出

```bash
npm run build   # 输出到 ../hermes_cli/web_dist/
```

---

## 二、Hermes-Studio (社区增强版)

**仓库**: `JPeetz/Hermes-Studio`
**Stars**: 262
**许可**: MIT
**Fork 自**: hermes-workspace

### 技术栈

React + TypeScript + TanStack, PWA, Vitest + Playwright, Docker

### CodeAgent 缺失的特性

| 特性 | 说明 | 优先级 |
|------|------|--------|
| **Audit Trail** | 跨会话 tool call + 用户消息 + 审批请求时间线，可按事件类型/日期筛选 | 高 |
| **Session History Archive** | 双栏会话浏览器，按日期/模型/Token/费用排序，懒加载完整消息线程 | 高 |
| **Cron Job Manager** | 定时调度 agent 任务，支持 SSE 实时流式输出到 Job card | 中 |
| **Multi-Agent Crews** | 命名 agent 组，并行任务分发，实时活动 feed | 低 |
| **Visual Workflow Builder** | DAG 节点图编排 agent 任务流水线，拓扑排序 | 低 |
| **Interactive Knowledge Graph** | 力导向图展示记忆关系，可缩放/拖拽 | 低 |
| **Execution Approvals UI** | 浏览器内审批 agent shell 命令，一次性/会话/永久三种范围 | 中 |
| **Cost Tracking** | 按 agent 统计 Token 用量和费用，分模型定价 | 高 (已有基础) |
| **MCP Server Management** | 从 UI 添加/编辑/删除 MCP 服务器，自动写 YAML | 中 |
| **Agent Library** | 创建/编辑/删除自定义 agent，含 system prompt/emoji/模型覆盖 | 低 |
| **Identity File Editor** | 浏览器内编辑 SOUL.md / persona.md / CLAUDE.md | 中 |
| **System Health Panel** | 底部固定栏显示 CPU/内存/磁盘/运行时间，颜色阈值 | 高 |
| **Operations Dashboard** | 统一视图展示所有运行中 agent | 低 |
| **Tasks / Kanban Board** | 五列看板 (Backlog → Todo → In Progress → Review → Done) | 中 |
| **Rate Limit Display** | API 频率限制显示 | 低 |
| **Event Analytics** | tool 调用频率统计、每日事件量柱状图 | 中 |
| **Patterns & Corrections Viewer** | 浏览 agent 学习到的模式和用户修正 | 低 |
| **Systemd Auto-start** | 一键生成/安装 systemd 服务 | 低 |
| **PWA 支持** | 可安装为桌面/移动端原生应用 | 中 |
| **8 主题系统** | 官方/经典/石板/单色 × 明暗变体 | 中 |
| **命令面板 Ctrl+K** | 快速搜索和导航 | 低 |

### Cron Job Manager 特色

- 自然语言 prompt + 定时调度
- 预设 (每15分钟/每小时/每天/每周) + 自定义 cron 表达式
- 投递渠道 (Telegram/Discord/Slack/Signal)
- 暂停/恢复/立即触发
- 手动触发时 SSE 实时流式输出工具事件

### 所有页面路由

```
/launch → LaunchPad
/skills → SkillGallery
/prompts → PromptsGallery
/hooks → HooksGallery
/plugins → PluginGallery
/config → ConfigHub
/dashboard → TaskDashboard
/analytics → Analytics
```

### CodeAgent 已有但可改进

| 现有页面 | 改进方向 |
|---------|---------|
| Analytics | 添加 tool 调用频率统计、事件分析 |
| ConfigHub | 添加 API Key 管理、MCP 服务器管理 |
| SkillGallery | 添加技能安装/卸载/开关 |
| TaskDashboard | 添加看板视图 |
| — | 新增 ChatPage (对话) |
| — | 新增 SessionsPage (会话历史双栏浏览) |
| — | 新增 SystemPage (系统健康) |
| — | 新增 LogsPage (日志查看) |

---

## 三、Hermes-HUDUI (浏览器版监控台)

**仓库**: `joeynyc/hermes-hudui`
**Stars**: 1.8k
**许可**: MIT

### 技术栈

Python 56.9% + TypeScript 40.1%, WebSocket 实时通信, 读 `~/.hermes/` 数据

### 特色功能

| 特性 | 说明 |
|------|------|
| **Hermes Replay** | agent 运行记录转为脱敏可分享产物 (JSON/Markdown/HTML/PNG)，Ed25519 签名 |
| **WebSocket 实时更新** | 数据变化自动推送，无需手动刷新 |
| **Gateway 工具可视化** | 显示 web 搜索、图片生成等工具的路由状态 |
| **19 个标签页** | 执行摘要/身份/记忆/技能/会话/回放/Cron/项目/健康/费用/模型分析/模式/修正/sudo 治理/实时聊天/OAuth/网关控制/插件/模型能力 |
| **中英文切换** | 内置语言切换，偏好持久化到 localStorage |
| **5 主题** | Neural Awakening (青)/Hermes Teal/Blade Runner (琥珀)/fsociety (绿)/Anime (紫)，可选 CRT 扫描线 |
| **键盘快捷键** | 1-9/0 切换标签，t 换主题，Ctrl+K 命令面板 |
| **Hermes Replay 远程发布** | 可选同步到 Git 静态页面，安全模式默认脱敏 |

### 对 CodeAgent 的启发

1. **WebSocket** 替代轮询 — Analytics 数据自动刷新，无需点击 Refresh
2. **命令面板 Ctrl+K** — 快速切换页面/主题，UX 提升明显
3. **多语言支持** — i18n 架构，支持中英文切换
4. **Replay 功能** — agent 运行记录导出为可分享的产物，团队协作和调试利器
5. **主题系统** — 5 套主题 + CRT 效果，比单一 glass-card 丰富

---

## 四、综合优先级建议

### P0 (当前差距最大，最应优先实现)

1. **ChatPage** — 浏览器内对话，SSE 流式输出 + tool call 渲染
2. **SessionsPage** — 双栏会话浏览 + 消息回放
3. **System Health Panel** — 底部固定栏系统状态
4. **Audit Trail** — tool call 时间线

### P1 (提升明显，次优)

5. **CronPage** — 定时任务调度 UI
6. **LogsPage** — 日志查看
7. **EnvPage** — API Key 管理
8. **PWA 支持**
9. **WebSocket 实时推送** (替代轮询)
10. **MCP Server Management**

### P2 (锦上添花)

11. **Identity File Editor** — 编辑 SOUL.md/persona.md/CLAUDE.md
12. **主题系统** — 多主题支持
13. **Event Analytics** — tool 调用频率统计
14. **命令面板 Ctrl+K**
15. **i18n 国际化** — 中英文切换