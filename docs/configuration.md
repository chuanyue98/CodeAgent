# Configuration Reference

CodeAgent uses `config.json` at the project root for all configuration. The file is automatically discovered by `ca_launcher.py`.

## Configuration File

```json
{
  "default_mode": "local",
  "language": "hybrid",
  "groups": { ... },
  "project_registry": [ ... ],
  "proxy": [ ... ],
  "paths": { ... },
  "schedules": [ ... ]
}
```

## Top-Level Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_mode` | string | `"local"` | Execution mode: `local` or `remote` |
| `language` | string | `"hybrid"` | Language preference: `hybrid`, `chinese`, `english` |
| `groups` | object | `{}` | Named configuration groups (see below) |
| `project_registry` | array | `[]` | Maps project paths to groups |
| `proxy` | array | `[]` | Proxy server configurations |
| `paths` | object | `{}` | Custom resource paths |
| `schedules` | array | `[]` | Cron-style scheduled tasks |
| `notifications` | object | `{}` | Webhook URLs to notify on schedule failure |

## Groups

Each group defines which skills, prompts, hooks, and plugins to inject:

```json
{
  "groups": {
    "codeagent": {
      "skills": [
        "base/task-authoring",
        "base/architect-planning",
        "base/commit-message",
        "base/skill-creator",
        "base/interview-model"
      ],
      "prompts": ["base"],
      "hooks": [],
      "plugins": ["base/superpowers"]
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `skills` | array | Skill directories to load |
| `prompts` | array | Prompt directories to inject |
| `hooks` | array | Hook directories to register |
| `plugins` | array | Plugin directories to activate |

### Default Groups

The project ships with four groups:

- **`codeagent`** — For developing CodeAgent itself
- **`work`** — General software development work
- **`web`** — Web/frontend development
- **`common`** — Default fallback group

## Project Registry

Maps project directory paths to configuration groups:

```json
{
  "project_registry": [
    { "path": "/home/user/projects/my-app", "group": "work" },
    { "path": "/home/user/projects/codeagent", "group": "codeagent" },
    { "path": "", "group": "common" }
  ]
}
```

Paths are matched in order. The first match is used. An empty string `""` serves as the fallback default.

## Proxy Configuration

CodeAgent supports HTTP and SOCKS5 proxies:

```json
{
  "proxy": [
    { "host": "127.0.0.1", "port": 1087 },
    { "host": "127.0.0.1", "port": 3065 }
  ]
}
```

The system auto-detects open ports and selects the first available proxy. Port 3066 is treated as SOCKS5 (commonly used by Karing); all others are HTTP proxies.

## Paths

Custom resource paths allow overriding default locations:

```json
{
  "paths": {
    "resource_root": "$CODEAGENT/custom_resources",
    "tasks": "custom_tasks"
  }
}
```

`$CODEAGENT` in paths is replaced with the project root directory.

## Schedules

Cron-style scheduled task definitions:

```json
{
  "schedules": [
    {
      "name": "daily_code_review",
      "cron": "0 9 * * 1-5",
      "task": "code_review",
      "engine": "gemini",
      "group": "work"
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `name` | Schedule identifier |
| `cron` | Cron expression for timing |
| `task` | Task name from `tasks/` |
| `engine` | Engine to use |
| `group` | Configuration group |

## Notifications

Webhook URLs to POST a JSON event to whenever a scheduled task fails to start
or finishes unsuccessfully. Delivery is best-effort: a broken or unreachable
URL is logged and skipped, never surfaced to the scheduler or the caller.

```json
{
  "notifications": {
    "webhooks": ["https://hooks.slack.com/services/…"]
  }
}
```

A single URL string is also accepted in place of the array. Each event posts
a JSON body shaped like:

```json
{
  "event": "schedule.failed",
  "schedule_id": "…",
  "task_name": "nightly-review",
  "engine": "claude",
  "workspace": "/path/to/project",
  "status": "failed: ..."
}
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `WOODPECKER_TOKEN` | For CI | Woodpecker CI personal access token |
| `GITHUB_TOKEN` | For CI | GitHub token (from `gh auth token`) |
| `CA_UI_DEV` | No | Set to `1` to have `ca ui` manage a Vite dev server instead of serving the built `web/frontend/dist/` |
| `CA_UI_HOST` | No | Bind host for `ca ui`'s API server. Default `127.0.0.1`; use `0.0.0.0` for container/remote access |
| `CA_CONFIG_PATH` | No | Overrides where `config.json` is read/written. Default is the repo root's `config.json` |
| `CA_SKIP_AUTO_REGISTER` | No | Suppresses the "run `ca project add`" hint when launching from an unregistered directory |
| `CA_DEBUG` | No | Set to `1` for verbose skill/hook/plugin/prompt scanner debug output |
| `CA_TASKS_ROOT` | No | Overrides the task-template directory (default: `tasks/` under the resolved resource root) |

A handful of others (`CA_E2E`, `CA_AGENT_GATEWAY_FAKE`, `CA_ROOT_DIR`, `CA_AGENT_LEGACY_FALLBACK`, `CA_PROJECT_GROUP`, `CODEAGENT_RESOURCE_ROOT`) exist mainly for internal tooling and tests — see `.env.example` for the full list with descriptions.
