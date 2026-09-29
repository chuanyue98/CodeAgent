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
| `-i`, `--interactive` | Open interactive launcher console |
| `--proxy` | Enable proxy from `config.json` |
| `-y`, `--yolo` | Enable YOLO (non-interactive) mode (default: on) |
| `-r`, `--resume` | Resume a previous session across any engine |
| `-s`, `--switch` | Switch/relay session to another engine |
| `--help` | Show help message |

## Engine Launch

Engines are launched explicitly. CodeAgent is a neutral multi-harness control plane with no implicit fallback engine.

```bash
ca                         # Open interactive launcher console (in terminal)
ca menu                    # Same as bare ca
ca -i                      # Explicit interactive mode
ca codex                   # Launch Codex engine
ca claude                  # Launch Claude engine
ca opencode                # Launch OpenCode engine
ca codebuddy               # Launch CodeBuddy engine
ca antigravity             # Launch Antigravity engine (alias: agy)
ca agy "Refactor this"     # Execute a task with Antigravity
ca claude -t refactor      # Run a pre-defined task with Claude
ca -r                      # Interactive list of recent sessions across all engines (like Claude Code)
ca -r 2                    # Resume the 2nd most recent session directly
ca resume                  # Subcommand alias for ca -r
ca -s codex                # Switch current session to Codex
ca switch codex            # Subcommand alias for ca -s
```

Arguments the launcher does not recognise go to the engine unchanged. Only when every
one of them is a plain word are they joined into the first message (`ca claude fix the
login`); as soon as a native flag or subcommand appears, the whole list is passed
through, because the launcher cannot tell which words are a flag's value.

CodeAgent's standards are **not** pushed into the engine by the launcher. They live in the
project's `AGENTS.md`, which `ca sync` writes, and every engine reads that file by itself:

| Engine | Reads project `AGENTS.md`? |
|--------|----------------------------|
| `claude` | yes (verified) |
| `codebuddy` | yes (verified) |
| `opencode` | yes (verified) |
| `codex` | yes — `AGENTS.md` is codex's own standard |
| `antigravity` | **no** — it reads no project-level file at all (verified) |

This replaced a per-engine injection layer (claude `--append-system-prompt-file`, codebuddy
`--append-system-prompt`, codex `-c developer_instructions=`, opencode
`OPENCODE_CONFIG_CONTENT`). On this machine only two of the five ever landed, codex and
codebuddy being blocked by their Windows `.cmd` wrappers, and failures were silent.

Several sessions may run in the same project at once. Linked skills, hooks and plugin links
are set up by each session and removed only when the last session using them exits.

**Engine-Specific Behavior:**

| Engine | CLI Tool | Notes |
|--------|----------|-------|
| `claude` | `claude` | Anthropic Claude Code CLI |
| `opencode` | `opencode` | OpenCode TUI (recommended) |
| `codex` | `codex` | OpenAI Codex CLI |
| `codebuddy` | `codebuddy` | Tencent CodeBuddy Code CLI |
| `antigravity` / `agy` | `agy` | Google Antigravity Next-Gen Agent CLI |

By default, YOLO mode is enabled (`-y` is appended automatically).

## Subcommands

### `ca sync`

Writes the resource group's standards into **this project's** `AGENTS.md`, and its skills
into each engine's user-level skill directory, so the bare engine commands load them
without going through `ca`.

```bash
ca sync                      # default_group from config.json, current directory
ca sync --group work         # another group
ca sync --project ../other   # point the standards at another project root
ca sync --engine claude      # only this engine's skills (repeatable)
ca sync --dry-run            # show what would change
ca sync --remove             # undo (deletes AGENTS.md if it only held our block)
ca sync --user               # legacy: per-engine user-level config, cleanup only
```

| What | Where |
|------|-------|
| Standards | `<project>/AGENTS.md` — one file, not one per engine |
| `claude` skills | `~/.claude/skills/` |
| `codex` skills | `$CODEX_HOME/skills/` (default `~/.codex`) |
| `opencode` skills | `~/.config/opencode/skills/` |
| `codebuddy` skills | `$CODEBUDDY_CONFIG_DIR/skills/` (default `~/.codebuddy`) |
| `antigravity` skills | `~/.gemini/config/skills/` |

Skills stay user-level because each engine lays its skill directory out differently, and
because the launcher already links the current project's skills into the project
(`.claude/skills` etc.) for the duration of a session — the user-level copy is the
fallback for running the engine without `ca`. Standards are project-scoped: writing them
user-level meant one managed block for every project, so a block belonging to another
project silently won.

Standards live in a `<!-- codeagent:begin group=... -->` block; content outside it is
preserved and re-syncing replaces only the block. Skills are links recorded in a
`.codeagent-links.json` manifest; an existing skill with the same name that CodeAgent did
not create is reported as a conflict and left untouched.

### `doctor`

Run environment health check and auto-repair.

```bash
ca doctor              # Check environment
ca doctor --fix        # Auto-repair issues
```

Checks are grouped into five sections (see `core/doctor.py`):

**Runtime**
- Python version — confirms Python 3.13+ is in use
- Engine availability — checks whether each provider CLI (`claude`, `opencode`, `codex`, `codebuddy`, `agy`) is found on `PATH`

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
- Stale injections — detects leftover `_ca_injected` markers in `.claude/settings.json`, `.opencode/settings.json`, or `.codex/settings.json` from a previous crashed session; `ca doctor --fix` restores the `.bak` backups

### `ui`

Start the Web UI analytics dashboard.

```bash
ca ui              # serve the built UI from web/frontend/dist/
ca ui --dev        # manage a Vite dev server instead, with live reload
```

Opens the dashboard at `http://127.0.0.1:8524`.

`ca ui` serves the static bundle in `web/frontend/dist/`, which is gitignored — after a pull that touches the frontend it warns that the bundle predates the sources, and you rebuild with `bun run build`.

`ca ui --dev` (equivalently `CA_UI_DEV=1`) starts Vite on `http://127.0.0.1:5173` and points you there, so frontend edits need no rebuild. It reuses a dev server already listening on that port, and falls back to the built bundle if Vite cannot start.

### `status`

Show what CodeAgent is currently doing for you, in one screen.

```bash
ca status
```

Three sections: the current directory, the resource group it resolves to (and whether
that group came from a `project_registry` rule or fell back to the default), whether the
project's `AGENTS.md` holds that group's standards, the declared
skills/prompts/hooks/plugins of that group, and every engine's CLI path.

The standards line replaces a per-launch status line that no longer exists. Three states:
the block is this project's group, the block belongs to a *different* group (the project
was re-registered, or the file came from elsewhere — the block has room for one group), or
there is no block yet, in which case the hint is `ca sync`. Because standards are one
project-level file rather than one per engine, this line lives under the project rather
than under each engine.

Unlike `ca doctor`, this reads only the config and the engine registry: it never
instantiates an engine or resolves resources, so it stays fast enough to run at any
time. Whether those resources actually resolve is doctor's question.

### `switch` (`ca -s`)

Continue an existing session in a different engine.

```bash
ca -s [target_engine] [selector]
ca switch [target_engine] [selector]
```

- When `target_engine` and `selector` are omitted, `ca -s` interactively previews recent sessions, defaults to `[1]` on Enter, and prompts for the target engine.
- When `target_engine` is provided without `selector` (e.g. `ca -s codex`), it displays candidate sessions with `[1] (default)` and confirms with Enter.
- Pass a selector directly (e.g. `ca -s codex 2`) or use `-y` to skip the confirmation prompt.

Converts the session into the target engine's native format and hands it straight to that engine's CLI — the CLI equivalent of the Web UI's convert-and-launch. The source session is left untouched.

| Option | Effect |
|---|---|
| `-y`, `--yes` | Skip confirmation prompt and immediately switch the most recent session |
| `--engine <name>` | Only consider sessions from this engine when picking the source |
| `--no-launch` | Convert and print the resume command, but do not start the engine |

Switching to the engine a session is already in skips conversion and resumes it as-is, rather than forking a duplicate.

### `history`

Session history management across all engine formats.

**List sessions:**
```bash
ca history list                 # All sessions
ca history list --engine opencode # Filter by engine
```

**Show session details:**
```bash
ca history show opencode <session_id>
ca history show claude <session_id>
```

**Convert between engine formats:**
```bash
ca history convert claude <session_id> opencode
ca history convert claude <session_id> codex
```

Supported engines for conversion: `claude`, `opencode`, `codex`, `codebuddy`, `antigravity` (or `agy`)

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

Manage external MCP servers across engines, install CodeAgent's internal FastMCP server into target engines, or serve CodeAgent itself as an MCP server:

```bash
# --- External MCP server management ---
ca mcp list                 # Every engine's configured servers
ca mcp list claude          # Just one engine

ca mcp add claude fs -- npx -y @modelcontextprotocol/server-filesystem /data
ca mcp add codex api --url https://example.com/mcp --transport http
ca mcp add codebuddy fs --env LOG=debug -- npx -y server-fs
ca mcp remove codebuddy fs

ca mcp sync claude                          # claude → other engines
ca mcp sync claude --to opencode --to codex # Only these targets
ca mcp sync claude --name filesystem        # Only this server
ca mcp sync claude --dry-run                # Preview without writing
ca mcp sync claude --overwrite              # Replace same-named servers instead of skipping

# --- CodeAgent Internal FastMCP Server Installation ---
ca mcp install                              # Auto-register CodeAgent MCP into all detected engines
ca mcp install --engine codex               # Register into a specific engine
ca mcp install --dry-run                    # Preview config modifications without writing
ca mcp install --no-write                   # Register in read-only mode (disables execution tools)
ca mcp install --remove                     # Unregister CodeAgent MCP from engines

# --- Serve CodeAgent as an MCP Server ---
ca mcp serve --allow-write                  # stdio mode (default, writable tools enabled)
ca mcp serve --http --port 8525             # HTTP / SSE transport mode
ca mcp serve --group work                   # Filter exposed skills by config resource group
ca mcp serve --trust-hooks                  # Enable arbitrary hook execution (highest risk)
```

#### `ca mcp install`

Registers CodeAgent's built-in FastMCP server into target engines' native configuration files (`claude`, `codex`, `opencode`, `antigravity`, `codebuddy`).
- Automatically resolves the repository path and executes via `uv run --project <root> python -m core.services.mcp_server_service --allow-write`.
- Target engines dynamically discover CodeAgent's cross-engine subtask delegation and session handoff tools.
- `--no-write`: Omits `--allow-write`, restricting the server to read-only tools (`skill_list`, `skill_read`, `ca://skills`).
- `--dry-run`: Previews the planned additions/removals across all engines without modifying files.
- `--remove`: Cleans up CodeAgent server entries from the target configuration files.

#### `ca mcp serve`

Exposes CodeAgent's local assets (skills, tasks) and coordination abilities according to the Model Context Protocol:
- **Read-only tools (always registered):**
  - `skill_list`: List available automation skills with title, category, and summary.
  - `skill_read(name)`: Read full `SKILL.md` instructions and scripts for a skill.
  - Resources: `ca://skills` (summary index), `ca://skill/{name}` (full skill instructions).
- **Execution tools (registered with `--allow-write`):**
  - `ca_delegate_subtask(engine, task, isolate_worktree=False)`: Delegate an execution subtask to a specified engine CLI (`claude`, `codex`, `opencode`, `codebuddy`, `agy`). Defaults to **in-place execution** (`isolate_worktree=False`) directly in the workspace so changes are immediately visible in your editor; set `isolate_worktree=True` for temporary git worktree sandboxing. Returns CLI execution output and captured `git diff`.
  - `ca_handoff_session(target_engine, prompt)`: Package active conversation messages and create a native resumed session in the target engine.
  - `skill_run(name, args)`: Run a skill script in a child process.
  - `task_run(task, engine, args)`: Execute a predefined CodeAgent task blueprint.
- **Privileged tools (registered with `--trust-hooks`):**
  - `hook_fire(hook_name, event)`: Execute arbitrary lifecycle hook scripts.

#### `ca mcp sync` & External Server Scope

Sync replays each definition through the target engine's own `mcp add` path, so every
engine keeps writing its own native config format — no config file is ever copied across.
A server already present in a target is skipped unless `--overwrite` is passed.

Two things to know about scope, both confirmed live rather than assumed from `--help`:

- **claude and codebuddy are per-project** (`.mcp.json`), so they
  read and write relative to the current directory.
- **codex and opencode are global** (`~/.codex/config.toml`,
  `~/.config/opencode/opencode.jsonc` or `.json`) — syncing *into* them affects every
  project on the machine, not just this one.
- **antigravity is global** (`~/.gemini/antigravity-cli/mcp_servers.json`).

If your `opencode.jsonc` contains comments, removing a server rewrites the file as plain
JSON and would drop them, so that one operation refuses and asks you to edit by hand.
Reads and syncs are unaffected.

One engine failing (its CLI missing from `PATH`, say) does not abort the others; each
result is reported per engine and the command exits non-zero if anything failed.

`ca doctor` reports servers that exist on some engines but not others, so drift
surfaces without diffing native config files by hand.

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
ca --proxy codex "task..."    # Codex with proxy
```

The system auto-detects active proxy ports from `config.json`.

## Examples

```bash
# Start a coding session with Claude
ca claude

# Run a code review task with Codex
ca codex -t code_review

# Launch the analytics dashboard
ca ui

# Create a new automation task
ca new automated-testing

# View OpenCode session history
ca history list --engine opencode

# Convert a Claude session for OpenCode
ca history convert claude <session_id> opencode

# Copy Claude's MCP servers to every other engine
ca mcp sync claude

# Register CodeAgent's built-in MCP server for cross-engine delegation
ca mcp install

# Check environment health
ca doctor --fix
```
