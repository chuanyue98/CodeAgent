# CodeAgent: The AI Sovereignty & Orchestration Framework

> **Philosophy**: Don't be a tenant in someone else's IDE. Own your prompts, own your standards, and switch your AI engine at will.

CodeAgent is a professional, CLI-first AI orchestration framework. It acts as an **engineering shell** that injects your private standards (The "Soul") and automation tools (The "Skills") into any LLM engine, ensuring consistent, high-quality engineering output.

---

## 🛠 Core Architecture: The Seven Pillars

1.  **Engines (`engines/`)**: Pluggable adapters for different AI agents.
    - `ca opencode`: **(Recommended)** Local npm CLI engine with TUI support.
    - `ca gemini`: Google AI-powered engineering driver.
    - `ca claude`: Anthropic-powered high-reasoning driver.
    - `ca codex`: OpenAI Codex CLI-powered engineering driver.
2.  **Prompts (`prompt/`)**: Your modular engineering "Soul".
    - `base/`: Core philosophy and values.
    - `coding/`: Language-specific and general coding standards.
    - `engineering/`: Workflow enhancements (Git, PR, File Safety).
3.  **Skills (`skills/`)**: Atomic, reusable automation capabilities.
    - Each skill contains its own `SKILL.md` (instruction) and `scripts/` (execution).
    - Dynamically mounted based on project context.
4.  **Plugins (`plugins/`)**: Domain-specific capability bundles.
    - Contains groups of skills, prompts (e.g., `GEMINI.md`), and hooks.
5.  **Hooks (`hooks/`)**: Lifecycle event triggers.
    - Execute commands during `session-start`, `pre-commit`, `post-tool`, etc.
6.  **Tasks (`tasks/`)**: High-level execution blueprints.
    - Pre-defined workflows like `refactor`, `code_review`, or `create_pr`.
7.  **Core (`core/`)**: The lightweight orchestration logic.
    - Handles dynamic prompt synthesis, resource resolution, and environment management.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.13+
- [Optional] `opencode-ai` installed via npm for the OpenCode engine.

### Launching Your Engine
CodeAgent automatically injects your private standards based on the current project directory.

```bash
python ca_launcher.py opencode              # Launch OpenCode TUI with standard injection
python ca_launcher.py gemini "Refactor this" # Execute a quick task with Gemini
python ca_launcher.py claude -t refactor     # Run a pre-defined refactor task with Claude
python ca_launcher.py ui                     # Start the Web UI & Analytics Dashboard
python ca_launcher.py doctor --fix           # Self-check and repair the environment
```

---

## 📊 Monitoring & Analytics

CodeAgent includes a built-in analytics engine to track usage across all drivers:
- **Multi-Engine Support**: Aggregates data from Claude, Gemini, Codex, and OpenCode.
- **Cost Estimation**: Estimates USD costs based on model-specific pricing.
- **Web Dashboard**: Use `python ca_launcher.py ui` to visualize trends, token usage, and session history.

---

## 🧘 Why CodeAgent?

1.  **Prompt Sovereignty**: Your engineering rules live in your repo as **Plain Markdown**. No hidden system prompts.
2.  **LLM Independence**: If a provider degrades their model, simply switch your flag. Your workflow remains unchanged.
3.  **Context Efficiency**: Only inject the prompts and skills you need. Save tokens and improve AI focus.
4.  **Local First**: No complex Docker setups required. Runs natively on your host with symbolic link safety.

---

## 📈 Structure
```text
.
├── core/          # Framework logic (Analytics, Services, Web)
├── engines/       # LLM Adapters (Gemini, Claude, OpenCode, Codex)
├── prompt/        # Modular standard groups (The Soul)
├── skills/        # Atomic automation capabilities (The Tools)
├── hooks/         # Lifecycle event triggers
├── web/           # Frontend (React/Vite) for the Analytics UI
└── tests/         # Quality guardrails
```
