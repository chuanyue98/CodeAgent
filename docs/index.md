# CodeAgent Documentation

CodeAgent is a CLI-first AI orchestration framework that injects your private engineering standards and automation skills into any LLM engine (Claude, OpenCode, Codex, CodeBuddy).

## Getting Started

| Guide | Description |
|-------|-------------|
| [Installation](installation.md) | System requirements, setup, and troubleshooting |
| [Quick Start](../README.md#quick-start) | Launch an engine, run tasks, use the dashboard |
| [Configuration](configuration.md) | Config file reference and examples |

## Reference

| Document | Description |
|----------|-------------|
| [CLI Commands](commands.md) | Full `ca` command reference |
| [Architecture](architecture.md) | Seven Pillars deep dive |
| [Multi-Agent Design](multi-agent-orchestration-design.md) | Crew/DAG orchestration design |

## Core Concepts

- **Engines** — Pluggable adapters (`engines/`) that wrap official CLI tools from AI providers
- **Prompts** — Modular markdown files (`prompt/`) forming your engineering "Soul"
- **Skills** — Atomic automation capabilities (`skills/`) with instructions and scripts
- **Hooks** — Lifecycle event triggers (`hooks/`) for session events
- **Plugins** — Domain-specific bundles (`plugins/`) of skills, prompts, and hooks
- **Tasks** — Execution blueprints (`tasks/`) for automated workflows
- **Core** — Orchestration logic (`core/`) for resource resolution, analytics, and web UI

## Project Layout

```text
.
├── ca_launcher.py      # CLI entry point (Click-based)
├── config.json         # Project configuration
├── core/               # Framework orchestration logic
│   ├── services/       # Gateway, Config, Runner, Scheduler, MCP, etc.
│   ├── web/            # FastAPI server + REST API
│   ├── analytics/      # Usage tracking & cost estimation
│   └── session_history/ # Session persistence & conversion
├── engines/            # AI provider adapters
├── prompt/             # Modular engineering standards
├── skills/             # Atomic automation capabilities
├── hooks/              # Lifecycle triggers
├── plugins/            # Domain bundles
├── tasks/              # Workflow blueprints
├── web/frontend/       # React + Vite + TypeScript dashboard
└── tests/              # Test suite (pytest)
```

## Development

- [README.md](../README.md#development) — Setup, linting, testing
- [Architecture](architecture.md) — System design and module relationships

## Design Documents

- [Multi-Agent Orchestration Design](multi-agent-orchestration-design.md) — Crew (DAG/Wave) coordination for multi-agent workflows
- [MCP CLI Spike Results](mcp-cli-spike-results.md) — Model Context Protocol integration research
- [Codex Hooks Spike Results](codex-hooks-spike-results.md) — How codex actually loads hooks (TOML shape, project trust)
- [Hermes Web UI Reference](hermes-web-ui-reference.md) — Web UI design reference
- [ChatPage CLI Spike Results](chatpage-cli-spike-results.md) — CLI chat page design research
