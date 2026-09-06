# CodeAgent: The AI Sovereignty & Orchestration Framework

> **Philosophy**: Don't be a tenant in someone else's IDE. Own your prompts, own your standards, and switch your AI engine at will.

CodeAgent is a professional, CLI-first AI orchestration framework. It acts as an **engineering shell** that injects your private standards (The "Soul") and automation tools (The "Skills") into any LLM engine, ensuring consistent, high-quality engineering output.

## Features

- **Multi-Engine Support** — Seamlessly switch between Claude, OpenCode, Codex, CodeBuddy, and Google Antigravity without changing your workflow
- **Prompt Sovereignty** — Your engineering rules live in your repo as Plain Markdown. No hidden system prompts
- **Modular Skills System** — Atomic, reusable automation capabilities with instruction files and executable scripts
- **Lifecycle Hooks** — Execute custom commands on the `before_tool` / `after_tool` events (e.g. branch protection, CI monitoring, pre-commit linting)
- **Plugin Architecture** — Bundle skills, prompts, and hooks into domain-specific capability packages
- **Analytics Dashboard** — Built-in web UI for monitoring usage, costs, and session history across all engines
- **Session Management** — List, view, and convert sessions between different engine formats
- **MCP Sync** — Configure an MCP server once, then `ca mcp sync <engine>` copies it into every other engine's native config
- **Background Task Management** — List (`ca ps`) and stop (`ca stop`) background task runs, or fan a task out across every registered project at once with `ca batch-run`
- **Scheduled Tasks** — Cron-like scheduler for automated recurring execution
- **Task Authoring** — Interview-style workflow for creating new task templates
- **YOLO Mode** — Non-interactive approval mode for automated pipelines
- **Proxy Support** — Auto-detects and configures HTTP/SOCKS5 proxies
- **Health Check** — `ca doctor --fix` for environment self-repair

## Architecture: The Seven Pillars

```
┌─────────────────────────────────────────────────────────────┐
│                     CodeAgent CLI (ca)                       │
│                  ca_launcher.py · Click-based                 │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│ Engines  │  Core    │ Prompts  │  Skills  │  Hooks/Plugins  │
│──────────│──────────│──────────│──────────│─────────────────│
│ opencode │ Services │  base/   │  base/   │  lifecycle      │
│ claude   │ Scanners │ coding/  │ custom/  │  triggers       │
│ codex    │ Analytics│ eng/     │          │  bundles        │
│codebuddy │ Web API  │          │          │                 │
│antigrav. │          │          │          │                 │
├──────────┴──────────┴──────────┴──────────┴─────────────────┤
│                    Tasks · Web UI · Tests                     │
└─────────────────────────────────────────────────────────────┘
```

1. **Engines** — Pluggable adapters for different AI agents (`engines/`),
   registered in one place (`core/engine_registry.py`):
   - `ca opencode`: Local npm CLI engine with TUI support **(Recommended)**
   - `ca claude`: Anthropic-powered high-reasoning driver
   - `ca codex`: OpenAI Codex CLI-powered engineering driver
   - `ca codebuddy`: Tencent engineering driver
   - `ca antigravity` (or `ca agy`): Google Next-Gen Agent CLI driver

2. **Prompts** — Your modular engineering "Soul" (`prompt/`)
   - `base/`: Core philosophy, language rules, and values
   - `coding/`: Language-specific and general coding standards
   - `engineering/`: Workflow enhancements (Git, PR, File Safety)

3. **Skills** — Atomic, reusable automation capabilities (`skills/`)
   - Each skill contains its own `SKILL.md` (instruction) and `scripts/` (execution)
   - Dynamically mounted based on project context via scanners

4. **Plugins** — Domain-specific capability bundles (`plugins/`)
   - Groups of skills, prompts, and hooks for specific domains

5. **Hooks** — Lifecycle event triggers (`hooks/`)
   - Execute commands on the `before_tool` / `after_tool` events (declared per-hook in `metadata.json`)

6. **Tasks** — High-level execution blueprints (`tasks/`)
   - Pre-defined workflows like `refactor`, `code_review`, `create_pr`

7. **Core** — Lightweight orchestration logic (`core/`)
   - Dynamic prompt synthesis, resource resolution, analytics, web server
   - Services: Agent Gateway, Config, Runner, Scheduler, MCP, and more

## Quick Start

### Prerequisites

- **Python 3.13+** and **[uv](https://docs.astral.sh/uv/)** (the project's
  dependency manager — do not use `pip`/`venv`/`conda`; see AGENTS.md).
- **At least one provider CLI, already installed and signed in.** CodeAgent drives the
  official CLIs — it does not talk to any API itself, and does not store your keys.
  Any one of `claude`, `opencode`, `codex`, or `codebuddy` is enough to start.
- [Optional] `bun` or `npm`, only if you want the Web UI.

### Installation

```bash
# --recurse-submodules matters: the bundled plugins live in a submodule,
# and a plain clone leaves plugins/base/superpowers empty.
git clone --recurse-submodules https://github.com/chuanyue98/CodeAgent.git
cd CodeAgent

uv sync                     # creates .venv and installs everything; or: uv sync --group dev

ca doctor --fix             # checks the provider CLIs, and creates config.json
```

`config.json` is gitignored — it holds machine-specific project paths — so a
fresh clone has none. `ca doctor --fix` seeds it from the tracked
`config.example.json`, which is also what your first `ca <engine>` run does.
Until it exists, no skills, prompts, or plugins are mounted.

Already cloned without `--recurse-submodules`? Run `git submodule update
--init --recursive`.

### First run (about two minutes)

```bash
cd /path/to/the/project/you/want/to/work/on
ca claude                   # or opencode / codex / codebuddy
```

The first launch in a new directory asks which resource group to bind it to, then hands
you the provider's own interface with your prompts and skills already injected. That is
the whole loop — everything below is optional.

### Launch an Engine

```bash
# Start the default engine (opencode) with project context injection
python ca_launcher.py

# Launch a specific engine
python ca_launcher.py opencode              # OpenCode TUI
python ca_launcher.py claude                # Anthropic Claude
python ca_launcher.py codex                 # OpenAI Codex
python ca_launcher.py codebuddy             # CodeBuddy Code
python ca_launcher.py antigravity           # Google Antigravity (alias: agy)

# Execute a task directly
python ca_launcher.py opencode "Refactor this module"
python ca_launcher.py claude -t refactor    # Run pre-defined task
python ca_launcher.py antigravity -t code_review
```

The `ca` command is also registered as a console script after `pip install -e .`:

```bash
ca              # Same as python ca_launcher.py
ca opencode     # Launch OpenCode engine
ca doctor --fix # Self-check and repair environment
ca ui           # Start Web UI dashboard
```

### Web UI Dashboard

The Web UI ships as source, not as a build artifact, so build it once after cloning:

```bash
cd web/frontend && bun install && bun run build   # or: npm install && npm run build
cd ../..
ca ui
```

Opens the dashboard at `http://127.0.0.1:8524`. Features:
- Usage trends and token consumption across all engines
- Cost estimation based on model-specific pricing
- Session history browser
- Task monitoring

### Switch Engines Mid-Conversation

The point of CodeAgent: a conversation outlives the tool it started in.

```bash
ca switch codex          # carry the most recent session here into Codex, and open it
ca switch claude 3       # session [3] from `ca history`, into Claude
ca switch codex --no-launch   # convert only, print the resume command
```

One step: it converts the session into the target engine's native format and
hands it straight to that engine's CLI. The source session is left untouched,
and switching to the engine a session is already in just resumes it.

### Session History

```bash
# List sessions for the current project
ca history list
ca history list --engine opencode  # Filter by engine

# View session details
ca history show opencode <session_id>

# Convert without launching (`ca switch` is usually what you want)
ca history convert claude <session_id> opencode
```

### Task Authoring

```bash
# Create a new task draft via interview workflow
ca new my-automation-task

# Run a pre-defined task
python ca_launcher.py opencode -t refactor
```

### Health Check

```bash
python ca_launcher.py doctor        # Check environment
python ca_launcher.py doctor --fix  # Auto-repair issues
```

### Discover Resources

```bash
# List what's available without opening the Web UI
ca resources list skills
ca resources list plugins
ca resources list hooks
ca resources list prompts

# Check enabled state against a specific resource group
ca resources list skills --group work
```

### Background Task Management

```bash
# List running background task runs (started via the CLI, Web UI, or scheduler)
ca ps
ca ps --all              # Include completed/failed/stopped runs

# Stop a running task by id
ca stop <task_id>

# Run one task across every registered project at once
ca batch-run code_review --engine claude --group work
ca batch-run code_review --engine claude --dry-run   # Preview targets without starting anything
```

See [docs/commands.md](docs/commands.md) for the full command reference.

## Configuration

CodeAgent uses a `config.json` for project-specific settings. It is gitignored;
`config.example.json` is the tracked template it is seeded from.

```json
{
  "default_mode": "local",
  "default_engine": "opencode",
  "language": "auto",
  "groups": {
    "codeagent": {
      "skills": ["base/task-authoring", "base/architect-planning"],
      "prompts": ["base"],
      "hooks": [],
      "plugins": ["base/superpowers"]
    }
  },
  "project_registry": [
    { "path": "/path/to/project", "group": "common" }
  ],
  "proxy": [
    { "host": "127.0.0.1", "port": 1087 }
  ],
  "schedules": []
}
```

| Field | Description |
|-------|-------------|
| `default_mode` | Execution mode (`local`, `remote`) |
| `language` | Language mode (`hybrid`, `chinese`, `english`) |
| `groups` | Named configurations mapping skills, prompts, hooks, and plugins |
| `project_registry` | Maps project paths to configuration groups |
| `proxy` | Proxy server configurations for network access |
| `schedules` | Cron-style scheduled task definitions |

See [docs/configuration.md](docs/configuration.md) for detailed reference.

## Project Structure

```text
.
├── ca_launcher.py         # CLI entry point
├── config.json            # Project configuration
├── core/                  # Framework logic
│   ├── analytics/         # Usage tracking & cost estimation
│   ├── services/          # Orchestration services (gateway, runner, scheduler, MCP)
│   ├── session_history/   # Session persistence & format conversion
│   ├── web/               # FastAPI web server & API routes
│   ├── engine_base/       # Base engine & mixins (config, prompts, links, settings)
│   ├── engine_registry.py # Declarative engine registry (single source of truth)
│   ├── doctor.py          # Health check & repair
│   └── *_scanner.py       # Resource discovery (skills, prompts, hooks, plugins)
├── engines/               # LLM Adapters
│   ├── start_claude_code.py
│   ├── start_opencode.py
│   └── start_codex.py
├── prompt/                # Modular standard groups (The Soul)
├── skills/                # Atomic automation capabilities (The Tools)
├── hooks/                 # Lifecycle event triggers
├── plugins/               # Domain capability bundles
├── tasks/                 # Pre-defined execution blueprints
├── web/                   # React/Vite frontend for Analytics UI
├── tests/                 # Quality guardrails (80+ test files)
└── docs/                  # Documentation
```

## Development

### Setup Development Environment

```bash
# Install with dev dependencies
uv sync --group dev
# or: pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Code Quality

```bash
# Linting
ruff check .

# Type checking (the two skill script trees intentionally contain duplicate
# module names, so type-check the application packages explicitly)
mypy core engines ca_launcher.py

# Tests
pytest

# Coverage
pytest --cov=core --cov-report=term-missing
```

### Frontend Development

The analytics dashboard is built with React + Vite + TypeScript + Tailwind:

```bash
# Day-to-day frontend work -- no build step, live reload:
ca ui --dev        # starts Vite (127.0.0.1:5173) and the API together

# Working on the production bundle instead:
cd web/frontend
bun install        # or npm install
bun run build      # Production build

# `web/frontend/dist/` is a build artifact and is not committed to git, so a
# fresh clone needs `bun run build` once before plain `ca ui` has a UI to
# serve. After a pull that touches the frontend, `ca ui` warns that the
# bundle predates the sources -- rebuild, or switch to `ca ui --dev`.
```

## Documentation

| Document | Description |
|----------|-------------|
| [docs/index.md](docs/index.md) | Documentation home |
| [docs/installation.md](docs/installation.md) | Installation guide |
| [docs/configuration.md](docs/configuration.md) | Configuration reference |
| [docs/architecture.md](docs/architecture.md) | Architecture deep dive |
| [docs/commands.md](docs/commands.md) | CLI command reference |
| [docs/deployment.md](docs/deployment.md) | Docker / production deployment guide |
| [docs/multi-agent-orchestration-design.md](docs/multi-agent-orchestration-design.md) | Multi-agent crew design |

## Why CodeAgent?

1. **Prompt Sovereignty** — Your engineering rules live in your repo as **Plain Markdown**. No hidden system prompts, no vendor lock-in.

2. **LLM Independence** — If a provider degrades their model or changes pricing, simply switch your flag. Your workflow, prompts, and skills remain unchanged.

3. **Context Efficiency** — Only inject the prompts and skills you need. Save tokens and improve AI focus by avoiding irrelevant context.

4. **Local First** — Runs natively on your host with symbolic link safety and zero infrastructure dependencies; no Docker setup is required to get started. If you do want a containerized deployment (e.g. for a shared/remote dashboard), CodeAgent ships a `Dockerfile` for that — see [docs/deployment.md](docs/deployment.md).

5. **Extensible by Design** — Add new engines, skills, prompts, hooks, or plugins without modifying the core framework.

## License

MIT License — see [LICENSE](LICENSE).
