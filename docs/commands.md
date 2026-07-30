# CLI Command Reference

The CodeAgent CLI is built with [Click](https://click.palletsprojects.com/) and provides a single `ca` command with multiple subcommands.

## Usage

```bash
ca [OPTIONS] [ENGINE] [ARGS]...
ca <command> [OPTIONS]
```

## Global Options

| Option | Description |
|--------|-------------|
| `--proxy` | Enable proxy from `config.json` |
| `-y`, `--yolo` | Enable YOLO (non-interactive) mode (default: on) |
| `--help` | Show help message |

## Engine Launch

If the first argument matches an engine name, it launches that engine. Otherwise, it forwards all arguments to the default engine (gemini).

```bash
ca                         # Launch default engine (gemini)
ca gemini                  # Launch Gemini engine
ca claude                  # Launch Claude engine
ca opencode                # Launch OpenCode engine
ca codex                   # Launch Codex engine
ca gemini "Refactor this"  # Execute a task with Gemini
ca claude -t refactor      # Run a pre-defined task with Claude
```

**Engine-Specific Behavior:**

| Engine | CLI Tool | Notes |
|--------|----------|-------|
| `gemini` | `gemini` | Google AI Studio CLI |
| `claude` | `claude` | Anthropic Claude Code CLI |
| `opencode` | `opencode` | OpenCode TUI (recommended) |
| `codex` | `codex` | OpenAI Codex CLI |

By default, YOLO mode is enabled (`-y` is appended automatically).

## Subcommands

### `doctor`

Run environment health check and auto-repair.

```bash
ca doctor              # Check environment
ca doctor --fix        # Auto-repair issues
```

Checks are grouped into five sections (see `core/doctor.py`):

**Runtime**
- Python version — confirms Python 3.13+ is in use
- Engine availability — checks whether each provider CLI (`claude`, `gemini`, `codex`, `opencode`) is found on `PATH`

**Configuration**
- `config.json` validity — confirms the file exists and parses correctly
- Resource directories — confirms `prompt/`, `skills/`, `hooks/`, `plugins/`, and `tasks/` exist

**Context Resolution**
- Skills resolution — confirms every skill declared in the active group resolves to a real directory
- Hooks resolution — confirms every hook declared in the active group resolves via its `metadata.json`
- Plugins resolution — confirms every plugin declared in the active group resolves

**Environment**
- Temp prompt file — confirms `.ca_prompt.tmp` is writable in the project root
- Proxy reachability — if a proxy is configured, checks whether any configured host:port is reachable
- Symlink/junction capability — confirms skill-linking will work (directory junctions on Windows, symlinks on Unix)

**Session Integrity**
- Stale injections — detects leftover `_ca_injected` markers in `.claude/settings.json`, `.gemini/settings.json`, `.opencode/settings.json`, or `.codex/settings.json` from a previous crashed session; `ca doctor --fix` restores the `.bak` backups

### `ui`

Start the Web UI analytics dashboard.

```bash
ca ui
```

Opens the dashboard at `http://127.0.0.1:8524` and serves the built static UI. Run Vite directly from `web/frontend` for development; set `CA_UI_DEV=1` when `ca ui` should manage that dev server.

### `history`

Session history management across all engine formats.

**List sessions:**
```bash
ca history list                 # All sessions
ca history list --engine gemini # Filter by engine
```

**Show session details:**
```bash
ca history show gemini <session_id>
ca history show claude <session_id>
```

**Convert between engine formats:**
```bash
ca history convert gemini <session_id> opencode
ca history convert claude <session_id> codex
```

Supported engines for conversion: `gemini`, `claude`, `opencode`, `codex`

### `new`

Create a new task draft using the interview workflow.

```bash
ca new my-task-name
```

Launches OpenCode with the task-authoring skill to guide you through creating a task blueprint. The resulting file is saved to `tasks/<name>.md`.

### `project`

Manage the project registry (`config.json`'s `project_registry`) without opening the Web UI or answering the interactive first-run prompt.

```bash
ca project add . --group work     # Register the current directory under "work"
ca project add /path/to/repo --group web
ca project list                   # List every registered project
ca project remove /path/to/repo   # Unregister a project
```

`ca project add` works in scripts and CI — no TTY required, unlike the interactive prompt that normally appears on first launch from an unregistered directory. If that prompt would otherwise be skipped (non-interactive session, or `CA_SKIP_AUTO_REGISTER` unset), a one-line hint pointing at `ca project add` is printed to stderr instead of failing silently.

### `resources`

Discover skills, plugins, hooks, and prompts without opening the Web UI.

```bash
ca resources list skills                # List all skills
ca resources list plugins
ca resources list hooks
ca resources list prompts

ca resources list skills --group work   # Check enabled state against a specific group
```

`ca resources list <kind>` accepts `skills`, `plugins`, `hooks`, or `prompts` for `<kind>`.
Each row shows the resource id and description, plus a marker for whether it is enabled
(`--group`, default `codeagent`) or, for hooks, whether it is currently active.

### `mcp`

Inspect MCP servers across engines, and copy them from one engine to the others so a
server only has to be configured once:

```bash
ca mcp list                 # Every engine's configured servers
ca mcp list claude          # Just one engine

ca mcp sync claude                          # claude → the other three
ca mcp sync claude --to gemini --to codex   # Only these targets
ca mcp sync claude --name filesystem        # Only this server
ca mcp sync claude --dry-run                # Preview without writing
ca mcp sync claude --overwrite              # Replace same-named servers instead of skipping
```

Sync replays each definition through the target engine's own `mcp add` path, so every
engine keeps writing its own native config format — no config file is ever copied across.
A server already present in a target is skipped unless `--overwrite` is passed.

Two things to know about scope, both confirmed live rather than assumed from `--help`:

- **claude and gemini are per-project** (`.mcp.json`, `.gemini/settings.json`), so they
  read and write relative to the current directory.
- **codex and opencode are global** (`~/.codex/config.toml`,
  `~/.config/opencode/opencode.jsonc` or `.json`) — syncing *into* them affects every
  project on the machine, not just this one.

If your `opencode.jsonc` contains comments, removing a server rewrites the file as plain
JSON and would drop them, so that one operation refuses and asks you to edit by hand.
Reads and syncs are unaffected.

One engine failing (its CLI missing from `PATH`, say) does not abort the others; each
result is reported per engine and the command exits non-zero if anything failed.

Adding and removing individual servers is currently Web UI only (`POST`/`DELETE
/api/mcp/{engine}`); the CLI covers listing and syncing.

### `ps` / `stop`

Manage background task runs (started via the CLI, Web UI, or scheduler) from the command line:

```bash
ca ps              # List running task runs
ca ps --all        # Include completed/failed/stopped runs
ca stop <task_id>  # Terminate a running task by id
```

### `batch-run`

Run one task across every registered project at once (optionally scoped to a resource group):

```bash
ca batch-run code_review --engine claude --group work
ca batch-run code_review --engine claude --dry-run   # Preview targets without starting anything
```

A project already running the same task is skipped rather than double-started.

## Proxy

Enable proxy support for engine sessions:

```bash
ca --proxy                    # Use default proxy from config
ca --proxy gemini "task..."   # Gemini with proxy
```

The system auto-detects active proxy ports from `config.json`.

## Examples

```bash
# Start a coding session with Claude
ca claude

# Run a code review task with Gemini
ca gemini -t code_review

# Launch the analytics dashboard
ca ui

# Create a new automation task
ca new automated-testing

# View Gemini session history
ca history list --engine gemini

# Convert a Claude session for OpenCode
ca history convert claude <session_id> opencode

# Copy Claude's MCP servers to every other engine
ca mcp sync claude

# Check environment health
ca doctor --fix
```
