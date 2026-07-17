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

Checks:
- Python version compatibility
- Required dependencies
- Configuration file validity
- Engine availability
- Frontend build status

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

# Check environment health
ca doctor --fix
```
