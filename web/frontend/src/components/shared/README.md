# shared/ — 前端组件与视觉约定

本目录是 Web UI 的唯一组件层。视觉 token 在 `src/index.css` 与 `tailwind.config.js`，这里存放「token 之上的决定」。

## 组件速查

| 组件 | 用途 | 关键 API |
|---|---|---|
| `Button` | 唯一按钮 | `variant: primary\|soft\|outline\|ghost\|destructive`、`size: sm\|md\|lg`、`loading?`、`icon?`；`type` 由调用方决定（表单内默认 submit）；无法用 `<button>` 的元素（Link/NavLink）走 `buttonClass.ts` 的 `buttonClass()` |
| `Field` / `Input` / `Textarea` / `Select` / `SearchInput` | 表单控件与标签栈 | `Field` 接 `label/hint/error`；焦点双信号（border + ring）在 `CONTROL` 基类里 |
| `Badge` | 徽章胶囊 | `variant="engine"` 必须走 present.ts 的 `eb()` 色板；`size: sm\|md` |
| `SectionLabel` | eyebrow 小标题 | 唯一规格：`text-[11px] font-semibold uppercase tracking-wider text-muted-foreground` |
| `EmptyState` | 空状态 | `icon/title/body/action`；`compact` 用于侧栏内搜索无结果等次要场景 |
| `StatusDot` | 状态点 | `tone: running\|success\|busy\|pending\|failed\|neutral`、`pulse?`（活体的软光环） |
| `GlassCard` | 卡片容器（扁平实色） | `variant: default\|feature\|flat`、`interactive?`；选择规则见组件 doc-comment |
| `ErrorBar` | 行内错误条 | `message/onDismiss?`；带重试的页面级失败用 `ErrorState` |
| `Modal` / `ConfirmDialog` / `Toast` / `ErrorState` / `LoadingState` / `FilterListSkeleton` / `Toggle` / `BatchActionBar` | 既有组件 | 沿用原 API |

## 约定

- **主题**：深色优先，浅色为可选项（跟随系统，或 `data-theme="light|dark"`，由 `utils/theme.ts` 读写）。语义 token（`--background`/`--card`/`--primary`…）在 `src/index.css`，三块结构：裸 `:root` 是深色，浅色在 `prefers-color-scheme: light` 与 `[data-theme="light"]` 里重定义。
- **随主题变色的调色板**：`slate`/`white` 与 `amber`/`red`/`emerald`… 在 `tailwind.config.js` 里被改成 CSS 变量（`themeScales` 插件生成），深色下色阶反向。所以 `bg-slate-50`、`text-amber-800` 这类类名不用改就跟随主题；新代码仍优先用语义 token（`bg-card`、`text-muted-foreground`、`border-border`）。
- **始终深色的表面**：终端与代码块用 `bg-term` / `text-term-fg` / `border-term-line`，不要用 `slate-900`（深色主题下它会变浅）。
- **引擎颜色**：`bg-engine-claude` 等（`--engine-*`），经 `terminalEngines.ts` 的 `dot`/`accent` 与 `analytics/present.ts` 的 `eb()`/`ec()` 使用，一个引擎一种色，处处一致。
- **状态色**：成功/警告用 `ok`/`warn`（`text-ok`、`bg-warn/15`），与强调色分开。
- **表面**：卡片是实色加细线（`glass-card*` 这三个类名保留，样式已是扁平的，没有模糊和阴影）。列表用「一张卡片 + `divide-y divide-border` 的行」，不要卡片套卡片。
- **圆角**：`--radius` = 12px，控件 `rounded-lg`，表面 `rounded-2xl`。
- **Markdown**：用 `prose prose-ca`（颜色走主题变量），不要 `prose-slate` / `prose-invert`。
- **Loading 三级制**：路由级首屏 = `LoadingState`；已知结构的筛选列表 = `FilterListSkeleton`；按钮/行内动作 = `Button loading` 或行内 `Loader2`。`animate-pulse` 只属于骨架屏，「运行中」的活性用 `StatusDot pulse`。
- **错误**：页面级（可重试）用 `ErrorState`；动作级用 `ErrorBar`；浮层用 `Toast`。一律 destructive token。
- **focus-visible**：全局 outline（index.css）是唯一焦点环，组件内不再手写。
- **响应式外壳**：`AppRail` 按 `useMediaQuery` 只挂一套布局（桌面左栏，或手机顶栏 + 底栏），不要用两套都渲染再靠 CSS 隐藏——命令面板挂载时监听 Ctrl+K，两份会同时弹出。

## 例外

`analytics/present.ts` 的 `eb()/ec()` 保持纯函数不依赖 React；`Badge` 只是它的壳。历史遗留的 slate 硬编码不做全局清扫——调色板已随主题变色；被组件吸收后，触碰到的文件顺手迁语义 token。
