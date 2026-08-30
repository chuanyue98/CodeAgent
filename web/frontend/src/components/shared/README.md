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
| `GlassCard` | 卡片容器 | `variant: default\|feature\|flat`、`interactive?`；选择规则见组件 doc-comment |
| `ErrorBar` | 行内错误条 | `message/onDismiss?`；带重试的页面级失败用 `ErrorState` |
| `Modal` / `ConfirmDialog` / `Toast` / `ErrorState` / `LoadingState` / `FilterListSkeleton` / `Toggle` / `BatchActionBar` | 既有组件 | 沿用原 API |

## 约定

- **圆角**：控件 `rounded-md/lg`，可交互块 `rounded-xl`，玻璃卡 `rounded-2xl`（= `var(--radius)`），hero 卡 `rounded-3xl`。
- **卡片 hover**：只走 `GlassCard interactive`（边框向 primary 暖色，无位移无阴影增长）。`active:scale-95` 仅属于 `Button primary`。
- **Loading 三级制**：路由级首屏 = `LoadingState`；已知结构的筛选列表 = `FilterListSkeleton`；按钮/行内动作 = `Button loading` 或行内 `Loader2`。`animate-pulse` 只属于骨架屏，「运行中」的活性用 `StatusDot pulse`。
- **错误**：页面级（可重试）用 `ErrorState`；动作级用 `ErrorBar`；浮层用 `Toast`。一律 destructive token。
- **focus-visible**：全局 outline（index.css）是唯一焦点环，组件内不再手写。
- **激活态**：tab/侧栏行选中统一用 `activeChip.ts` 的 `ACTIVE_CHIP`。
- **暗色扩展位**：`.glass-card*` 只消费 `--glass-*` 变量；未来暗色 = 一个 `.dark` 块重定义玻璃变量 + HSL 组 + 大气 token，组件零改动。

## 例外

`analytics/present.ts` 的 `eb()/ec()` 保持纯函数不依赖 React；`Badge` 只是它的壳。历史遗留的 slate 硬编码不做全局清扫——被组件吸收后，触碰到的文件顺手迁 token（slate-500→`text-muted-foreground`、slate-200→`border`、slate-100→`bg-muted`）。但 `shared/` 自身零硬编码色：组件层要是留了 slate，暗色主题的一处变量覆盖就盖不住它。
