# CodeAgent Web 界面

React、TypeScript 与 Vite 构建的管理界面，包含会话、终端、任务、资源和用量统计。

在本目录运行：

```sh
bun install --frozen-lockfile
bun run dev
bun run typecheck
bun run lint
bun run test
bun run build
```

开发服务器监听 `127.0.0.1:5173`，将 `/api`（包括 WebSocket）代理到
`127.0.0.1:8524`。在仓库根目录用 `uv run ca ui` 启动后端。
生产构建输出到 `dist/`，由后端提供静态文件服务。

单元测试在 `src/__tests__/`；Playwright 测试在 `e2e/`，使用隔离数据和假引擎。
端到端测试启动脚本依赖 Bash，请在 Linux/WSL 或 CI 环境运行 `bun run e2e`。
