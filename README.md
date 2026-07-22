# CodeAgent: The AI Sovereignty & Orchestration Framework

> **Philosophy**: Don't be a tenant in someone else's IDE. Own your prompts, own your standards, and switch your AI engine at will.

CodeAgent is a professional, CLI-first AI orchestration framework. It acts as an **engineering shell** that injects your private standards (The "Soul") and automation tools (The "Skills") into any LLM engine, ensuring consistent, high-quality engineering output.

## Features

- **Multi-Engine Support** — Seamlessly switch between Claude, Gemini, Codex, and OpenCode without changing your workflow
- **Prompt Sovereignty** — Your engineering rules live in your repo as Plain Markdown. No hidden system prompts
- **Modular Skills System** — Atomic, reusable automation capabilities with instruction files and executable scripts
- **Lifecycle Hooks** — Execute custom commands on `session-start`, `pre-commit`, `post-tool`, and more
- **Plugin Architecture** — Bundle skills, prompts, and hooks into domain-specific capability packages
- **Analytics Dashboard** — Built-in web UI for monitoring usage, costs, and session history across all engines
- **Session Management** — List, view, and convert sessions between different engine formats
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
│ gemini   │ Services │  base/   │  base/   │  lifecycle      │
│ claude   │ Scanners │ coding/  │ custom/  │  triggers       │
│ opencode │ Analytics│ eng/     │          │  bundles        │
│ codex    │ Web API  │          │          │                 │
├──────────┴──────────┴──────────┴──────────┴─────────────────┤
│                    Tasks · Web UI · Tests                     │
└─────────────────────────────────────────────────────────────┘
```

1. **Engines** — Pluggable adapters for different AI agents (`engines/`)
   - `ca opencode`: Local npm CLI engine with TUI support **(Recommended)**
   - `ca gemini`: Google AI-powered engineering driver
   - `ca claude`: Anthropic-powered high-reasoning driver
   - `ca codex`: OpenAI Codex CLI-powered engineering driver

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
   - Execute commands during `session-start`, `pre-commit`, `post-tool`, etc.

6. **Tasks** — High-level execution blueprints (`tasks/`)
   - Pre-defined workflows like `refactor`, `code_review`, `create_pr`

7. **Core** — Lightweight orchestration logic (`core/`)
   - Dynamic prompt synthesis, resource resolution, analytics, web server
   - Services: Agent Gateway, Config, Runner, Scheduler, MCP, and more

## Quick Start

### Prerequisites

- Python 3.13+
- [Optional] `opencode` installed via npm for the OpenCode engine

### Installation

```bash
# Clone the repository
git clone https://github.com/chuanyue98/CodeAgent.git
cd CodeAgent

# Create a virtual environment (recommended) and install
python -m venv .venv
source .venv/bin/activate

# Install with uv (recommended) or pip
uv sync
# or: pip install -e .
```

### Launch an Engine

```bash
# Start the default engine (gemini) with project context injection
python ca_launcher.py

# Launch a specific engine
python ca_launcher.py opencode              # OpenCode TUI
python ca_launcher.py gemini                # Google Gemini
python ca_launcher.py claude                # Anthropic Claude
python ca_launcher.py codex                 # OpenAI Codex

# Execute a task directly
python ca_launcher.py gemini "Refactor this module"
python ca_launcher.py claude -t refactor    # Run pre-defined task
python ca_launcher.py opencode -t code_review
```

The `ca` command is also registered as a console script after `pip install -e .`:

```bash
ca              # Same as python ca_launcher.py
ca opencode     # Launch OpenCode engine
ca doctor --fix # Self-check and repair environment
ca ui           # Start Web UI dashboard
```

### Web UI Dashboard

```bash
python ca_launcher.py ui
```

Opens the analytics dashboard at `http://127.0.0.1:8524`. Features:
- Usage trends and token consumption across all engines
- Cost estimation based on model-specific pricing
- Session history browser
- Task monitoring

### Session History

```bash
# List sessions for the current project
ca history list
ca history list --engine gemini    # Filter by engine

# View session details
ca history show gemini <session_id>

# Convert sessions between engine formats
ca history convert gemini <session_id> opencode
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

## Configuration

CodeAgent uses a `config.json` for project-specific settings:

```json
{
  "default_mode": "local",
  "language": "hybrid",
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
│   ├── engine_base.py     # Base engine & environment manager
│   ├── doctor.py          # Health check & repair
│   └── scanners/          # Resource discovery (skills, prompts, hooks, plugins)
├── engines/               # LLM Adapters
│   ├── start_gemini.py
│   ├── start_claude_code.py
│   ├── start_opencode.py
│   └── start_codex.py
├── prompt/                # Modular standard groups (The Soul)
├── skills/                # Atomic automation capabilities (The Tools)
├── hooks/                 # Lifecycle event triggers
├── plugins/               # Domain capability bundles
├── tasks/                 # Pre-defined execution blueprints
├── web/                   # React/Vite frontend for Analytics UI
├── tests/                 # Quality guardrails (31 test files)
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
cd web/frontend
bun install        # or npm install
bun run dev        # Start Vite directly for development
bun run build      # Production build

# `web/frontend/dist/` is a build artifact and is not committed to git.
# From the repository root, `ca ui` serves that build, so run `bun run build`
# (or `npm run build`) at least once after cloning. Set CA_UI_DEV=1 only when
# you explicitly want it to manage a Vite dev server instead.
```

## Documentation

| Document | Description |
|----------|-------------|
| [docs/index.md](docs/index.md) | Documentation home |
| [docs/installation.md](docs/installation.md) | Installation guide |
| [docs/configuration.md](docs/configuration.md) | Configuration reference |
| [docs/architecture.md](docs/architecture.md) | Architecture deep dive |
| [docs/commands.md](docs/commands.md) | CLI command reference |
| [docs/multi-agent-orchestration-design.md](docs/multi-agent-orchestration-design.md) | Multi-agent crew design |

## Why CodeAgent?

1. **Prompt Sovereignty** — Your engineering rules live in your repo as **Plain Markdown**. No hidden system prompts, no vendor lock-in.

2. **LLM Independence** — If a provider degrades their model or changes pricing, simply switch your flag. Your workflow, prompts, and skills remain unchanged.

3. **Context Efficiency** — Only inject the prompts and skills you need. Save tokens and improve AI focus by avoiding irrelevant context.

4. **Local First** — No complex Docker setups required. Runs natively on your host with symbolic link safety and zero infrastructure dependencies.

5. **Extensible by Design** — Add new engines, skills, prompts, hooks, or plugins without modifying the core framework.

## License

MIT License — see [LICENSE](LICENSE).
