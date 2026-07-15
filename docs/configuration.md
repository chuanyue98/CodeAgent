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

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `WOODPECKER_TOKEN` | For CI | Woodpecker CI personal access token |
| `GITHUB_TOKEN` | For CI | GitHub token (from `gh auth token`) |
