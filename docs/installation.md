# Installation Guide

## System Requirements

- **OS**: Linux, macOS, Windows
- **Python**: 3.13+
- **Package Manager**: `uv` (recommended) or `pip`
- **Optional**: Node.js ≥18 (for OpenCode engine), `bun` or `npm` (for frontend dev)

## Standard Installation

### 1. Clone the Repository

```bash
git clone https://github.com/chuanyue98/CodeAgent.git
cd CodeAgent
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# or: .venv\Scripts\activate  # Windows
```

### 3. Install Dependencies

Using `uv` (recommended):

```bash
uv sync
```

Using `pip`:

```bash
pip install -e .
```

### 4. Verify Installation

```bash
python ca_launcher.py doctor
```

## Development Installation

Install with dev dependencies for linting, type checking, and testing:

```bash
# uv
uv sync --group dev

# pip
pip install -e ".[dev]"

# Install pre-commit hooks (optional)
pre-commit install
```

## Frontend Setup

The analytics dashboard requires additional frontend dependencies:

```bash
cd web/frontend
bun install      # recommended
# or: npm install
```

## Optional Dependencies

### OpenCode Engine

```bash
npm install -g opencode-ai
```

### Claude Engine

Requires the `claude` CLI tool. See [Anthropic's documentation](https://docs.anthropic.com/en/docs/claude-code/overview) for installation.

### Codex Engine

Requires the `codex` CLI tool. See [OpenAI's documentation](https://platform.openai.com/docs/guides/codex) for installation.

## Configuration

After installation, copy and customize the environment template if you use
the optional repository automation integrations:

```bash
cp .env.example .env
# Edit .env with your API tokens
```

See [Configuration Reference](configuration.md) for full details.
