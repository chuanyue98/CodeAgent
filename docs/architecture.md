# Architecture

CodeAgent is built on a **Seven Pillars** architecture that cleanly separates concerns between AI engine adapters, engineering standards, automation capabilities, and orchestration logic.

## Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Layer (ca)                            │
│            ca_launcher.py · Click · Command Routing               │
├──────────────┬──────────────┬────────────────────────────────────┤
│   Engines    │     Core     │         Resource Layers             │
│──────────────│──────────────│────────────────────────────────────│
│  gemini      │  Services    │  ┌──────────┐ ┌──────────┐        │
│  claude      │  Scanners    │  │ Prompts  │ │  Skills  │        │
│  opencode    │  Analytics   │  │ (Soul)   │ │ (Tools)  │        │
│  codex       │  Web API     │  └──────────┘ └──────────┘        │
│              │              │  ┌──────────┐ ┌──────────┐        │
│              │              │  │  Hooks   │ │  Plugins │        │
│              │              │  │(Lifecycle)│ │ (Bundles)│        │
│              │              │  └──────────┘ └──────────┘        │
├──────────────┴──────────────┴────────────────────────────────────┤
│                     Tasks · Web UI · Tests                        │
└─────────────────────────────────────────────────────────────────┘
```

## Seven Pillars

### 1. Engines (`engines/`)

Pluggable adapters that wrap official CLI tools from each AI provider:

| Engine | Script | CLI Tool |
|--------|--------|----------|
| Gemini | `engines/start_gemini.py` | `gemini` CLI |
| Claude | `engines/start_claude_code.py` | `claude` CLI |
| OpenCode | `engines/start_opencode.py` | `opencode` CLI |
| Codex | `engines/start_codex.py` | `codex` CLI |

Each engine script:
1. Discovers the project root and loads `config.json`
2. Scans for skills, prompts, hooks, and plugins via `core/` scanners
3. Synthesizes a combined system prompt from all active resources
4. Launches the vendor CLI tool with the synthesized prompt injected

### 2. Core (`core/`)

The orchestration hub containing:

**Services (`core/services/`)**
- `agent_gateway.py` + `agent_protocol.py` + `agent_store.py` — Unified adapter gateway abstracting provider differences
- `agent_adapters/` — Individual provider adapters (Claude, Codex, OpenCode)
- `config_service.py` — Configuration loading and resolution
- `runner_service.py` — Task subprocess management with orphan reaping
- `schedule_service.py` / `scheduler_loop.py` — Cron-like scheduled execution
- `mcp_service.py` — Model Context Protocol integration
- `hook_service.py` / `plugin_service.py` / `skill_service.py` / `prompt_service.py` — Resource management
- `task_service.py` — Task execution service

**Scanners (`core/`)**
- `skill_scanner.py` — Discovers skill directories and loads their `SKILL.md`
- `prompt_scanner.py` — Collects prompt markdown files
- `hook_scanner.py` — Finds hook configurations
- `plugin_scanner.py` — Resolves plugin bundles

**Analytics (`core/analytics/`)**
- Tracks usage across all engine drivers
- Estimates USD costs based on model-specific pricing
- Aggregates data for the web dashboard

**Session History (`core/session_history/`)**
- Stores and retrieves session data
- Converts between different engine formats (Gemini ↔ Claude ↔ Codex ↔ OpenCode)
- `session_finder.py` — Locates sessions by project path

**Web Server (`core/web/`)**
- FastAPI application with REST API endpoints
- Routes for analytics data, task monitoring, and session management
- Static file serving for the React frontend build

### 3. Prompts (`prompt/`)

Your engineering "Soul" — modular markdown files organized by domain:

```text
prompt/
├── base/               # Core philosophy & values
│   ├── general.basic.md
│   └── ...
├── coding/             # Language-specific standards
│   ├── python.md
│   ├── typescript.md
│   └── ...
└── engineering/        # Workflow enhancements
    ├── git.md
    ├── pr.md
    └── file-safety.md
```

Prompts are injected into every AI session to ensure consistent engineering standards regardless of the underlying LLM.

### 4. Skills (`skills/`)

Atomic automation capabilities, each with structured instructions:

```text
skills/
└── base/
    ├── task-authoring/       # Create task blueprints
    │   ├── SKILL.md          # Instructions injected into AI
    │   └── scripts/          # Optional executable scripts
    ├── architect-planning/   # Architecture design workflow
    ├── commit-message/       # Git commit message generation
    ├── skill-creator/        # New skill development
    └── interview-model/      # Interview-style requirements gathering
```

Each skill is a self-contained directory with a `SKILL.md` (YAML frontmatter + markdown instructions) and optional `scripts/` for execution.

### 5. Hooks (`hooks/`)

Lifecycle event triggers that execute commands at specific points:

| Hook Name | Trigger | Purpose |
|-----------|---------|---------|
| `branch-protection` | `pre-commit` | Enforce branch naming policies |
| `ci-monitor` | `post-tool` | Check CI status after tool calls |
| `pre-commit` | `pre-commit` | Run checks before commits |

### 6. Plugins (`plugins/`)

Domain-specific bundles that group related skills, prompts, and hooks:

- **`base/superpowers`** — The Superpowers enhancement suite for AI-assisted development

### 7. Tasks (`tasks/`)

High-level execution blueprints that define multi-step workflows:

```yaml
# tasks/code_review.md
task: code_review
engine: gemini
steps:
  - analyze: Read all changed files
  - review: Check for bugs, security, and style
  - report: Generate review summary
```

## Key Design Decisions

### CLI Wrapper Pattern

CodeAgent wraps official CLI tools rather than connecting to LLM APIs directly. This means:
- No need to implement agent loops — the vendor CLI handles conversation state
- Upstream updates are automatically inherited
- Multi-agent coordination must work at the task boundary level (DAG/wave pattern), not via in-process messaging

### Resource Injection

When an engine launches, CodeAgent:
1. Determines the project context via `config.json`'s `project_registry`
2. Scans the active group for skills, prompts, hooks, and plugins
3. Synthesizes a unified prompt combining all active resources
4. Passes the synthesized prompt to the vendor CLI

This ensures every session starts with your complete engineering context.

### Analytics Pipeline

1. Each engine session emits structured logs
2. `core/analytics/` processes logs into usage metrics
3. Metrics are stored and exposed via the FastAPI REST API
4. The React frontend visualizes trends, costs, and session history

## Data Flow

```text
User Input
    │
    ▼
ca_launcher.py ──► Engine Script ──► Vendor CLI (AI)
    │                                      │
    ├── config.json ◄──────────────────────┘
    │                                      │
    ├── core/scanners ◄────────────────────┘
    │    (skills, prompts, hooks, plugins)  │
    │                                      │
    └── core/services ◄────────────────────┘
         (agent_gateway, runner, analytics)
```
