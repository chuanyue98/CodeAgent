# CodeAgent Web UI

React/Vite frontend for the CodeAgent local dashboard. It covers launch controls,
resource galleries, configuration, tasks, and analytics.

## Package Manager

Use Bun. The repository intentionally tracks `bun.lock` as the single frontend
lockfile so local development matches CI.

```bash
bun install --frozen-lockfile
```

## Development

Start the frontend dev server:

```bash
bun run dev
```

Start the backend API from the repository root:

```bash
python ca_launcher.py ui
```

## Checks

```bash
bun run lint
bun run test
bun run build
```
