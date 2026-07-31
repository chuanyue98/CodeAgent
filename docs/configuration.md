# Configuration Reference

CodeAgent uses `config.json` at the project root for all configuration. The file is automatically discovered by `ca_launcher.py`.

## Configuration File

```json
{
  "default_mode": "local",
  "default_engine": "gemini",
  "language": "auto",
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
| `default_engine` | string | `"gemini"` | Engine `ca` launches when none is named (see below) |
| `language` | string | auto | UI language: `en`, `zh`, or `auto` (see below) |
| `groups` | object | `{}` | Named configuration groups (see below) |
| `project_registry` | array | `[]` | Maps project paths to groups |
| `proxy` | array | `[]` | Proxy server configurations |
| `paths` | object | `{}` | Custom resource paths |
| `schedules` | array | `[]` | Cron-style scheduled tasks |
| `notifications` | object | `{}` | Webhook URLs to notify on schedule failure |

### Default Engine

`default_engine` picks which engine a bare `ca` (or `ca <free-form prompt>`)
starts. Accepted values are `claude`, `gemini`, `opencode`, and `codex`; naming
an engine explicitly — `ca claude ...` — always wins over this setting.

Without it, `ca` always started `gemini`, so anyone working primarily in
another engine had to name it on every single invocation.

An unrecognized value does not abort the launch: CodeAgent prints a warning
naming the known engines and falls back to `gemini`.

### Language

`language` sets the language of user-facing CLI output. Accepted values are
`en`, `zh`, or `auto` (equivalently: omitted, or the legacy value `hybrid`).
Locale forms like `zh-CN` and `en_US` are accepted too.

Resolution order, first match wins:

1. The `CA_LANG` environment variable — overrides everything for one
   invocation, e.g. `CA_LANG=en ca doctor`. The launcher also uses it to pass
   its choice down to the engine subprocesses, so both halves of a session
   speak the same language.
2. `language` in `config.json`.
3. The OS locale (`LANGUAGE` / `LC_ALL` / `LC_MESSAGES` / `LANG`).
4. English.

This setting previously existed in `config.json` but nothing read it — output
was a fixed mix of English and Chinese regardless of what you set.

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

#### Hook support by engine

Hooks are declared once per group, but not every engine can run them. The
canonical `before_tool` / `after_tool` events map to each engine's own names at
launch:

| Engine | Target file | Events | Status |
|---|---|---|---|
| claude | `.claude/settings.json` | `PreToolUse` / `PostToolUse` | Supported |
| gemini | `.gemini/settings.json` | `BeforeTool` / `AfterTool` | Supported |
| codex | `.codex/config.toml` | `PreToolUse` / `PostToolUse` | Supported — requires project trust (see below) |
| opencode | `.opencode/plugins/ca_hooks_bridge.js` | `tool.execute.before` / `tool.execute.after` | Supported via a generated bridge plugin |

Codex only loads a project's `.codex/config.toml` — hooks included — if the
project is marked trusted in the user-level `~/.codex/config.toml`. Without it,
codex starts normally and silently ignores the hooks, so CodeAgent prints a
warning with the entry to add:

```toml
[projects."E:\\path\\to\\project"]
trust_level = "trusted"
```

See [Codex Hooks Spike Results](codex-hooks-spike-results.md) for how this was
verified.

#### How the OpenCode bridge works

OpenCode has no shell-command hook mechanism — its hooks are JavaScript
functions returned by a plugin module. CodeAgent therefore generates
`.opencode/plugins/ca_hooks_bridge.js` at launch and removes it on exit. The
bridge spawns each hook with the same Claude-shaped JSON payload the other
engines send, so **an existing hook runs unmodified**:

```json
{
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "opencode_tool_name": "bash",
  "tool_input": { "command": "git commit -m ..." },
  "session_id": "..."
}
```

Two details worth knowing:

- **Tool names are normalized.** OpenCode's shell tool is `bash`, but the
  shipped hooks match Claude's `Bash`, so the bridge maps known ids across and
  passes unknown ones through untouched. The raw id is always available as
  `opencode_tool_name`.
- **A denial surfaces as a tool error.** `tool.execute.before` returns void, so
  throwing is the only way to stop a call. The hook's
  `permissionDecisionReason` (or its stderr, for the exit-code-2 convention)
  becomes the error message the model sees. For `after_tool` the tool has
  already run, so feedback is appended to the tool output instead of discarding
  a valid result.

A hook that cannot start, or that exceeds the 600s timeout, is logged to stderr
and **fails open** — a broken hook will not brick the session.

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
| `CA_UI_TOKEN` | No | Pins the Web UI token instead of using the generated `~/.codeagent/ui-token`. For containers and test harnesses |
| `CA_UI_AUTH` | No | Set to `0`/`off` to disable Web UI **token** checking. Host and Origin checks still apply. Only when an authenticating proxy sits in front |
| `CA_UI_ALLOWED_HOSTS` | No | Comma-separated extra `Host` values the Web UI accepts, for deployments reached under a real hostname. `*` accepts any Host and disables the DNS-rebinding defence |
| `CA_CONFIG_PATH` | No | Overrides where `config.json` is read/written. Default is the repo root's `config.json` |
| `CA_SKIP_AUTO_REGISTER` | No | Suppresses the "run `ca project add`" hint when launching from an unregistered directory |
| `CA_DEBUG` | No | Set to `1` for verbose skill/hook/plugin/prompt scanner debug output |
| `CA_TASKS_ROOT` | No | Overrides the task-template directory (default: `tasks/` under the resolved resource root) |

A handful of others (`CA_E2E`, `CA_AGENT_GATEWAY_FAKE`, `CA_ROOT_DIR`, `CA_AGENT_LEGACY_FALLBACK`, `CA_PROJECT_GROUP`, `CODEAGENT_RESOURCE_ROOT`) exist mainly for internal tooling and tests — see `.env.example` for the full list with descriptions.
