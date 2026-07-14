#!/usr/bin/env bash
set -euo pipefail

# Launches the CodeAgent backend, serving the already-built frontend
# (dist/), fully isolated from the developer's real data. Used as
# playwright.config.ts's webServer.command — see e2e/fixtures/README.md
# and docs/mcp-cli-spike-results.md for why isolation here means more than
# just CA_CONFIG_PATH: mcp_service.py's codex/opencode paths and the
# session-history parsers read $HOME directly, so $HOME itself is
# redirected to a scratch dir alongside the app's own CA_*_ROOT vars.
#
# Required before running: `npm run build` in web/frontend (produces dist/).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$(dirname "$FRONTEND_DIR")")"

if [ ! -f "$FRONTEND_DIR/dist/index.html" ]; then
  echo "❌ web/frontend/dist not found — run 'npm run build' in web/frontend first." >&2
  exit 1
fi

SCRATCH="$(mktemp -d -t codeagent-e2e-XXXXXX)"

cleanup() {
  local ec=$?
  kill "${SERVER_PID:-}" 2>/dev/null || true
  wait "${SERVER_PID:-}" 2>/dev/null || true
  rm -rf "$SCRATCH"
  exit "$ec"
}
trap cleanup EXIT INT TERM

export HOME="$SCRATCH/home"
mkdir -p "$HOME"

export CA_CONFIG_PATH="$SCRATCH/config.json"
export CA_TASKS_ROOT="$SCRATCH/tasks"
export CA_SKILLS_ROOT="$SCRATCH/skills"
export CA_PROMPTS_ROOT="$SCRATCH/prompts"
export CA_HOOKS_ROOT="$SCRATCH/hooks"
export CA_PLUGINS_ROOT="$SCRATCH/plugins"

# Tells core/web/server.py to mount the /api/__e2e_reset route so per-test
# Playwright cleanup can restore a clean baseline (see core/web/routers/e2e.py).
export CA_E2E=1
export CA_AGENT_GATEWAY_FAKE=1
export CA_AGENT_DB="$SCRATCH/agent-gateway.sqlite3"

mkdir -p "$CA_TASKS_ROOT" "$CA_SKILLS_ROOT" "$CA_PROMPTS_ROOT" "$CA_HOOKS_ROOT" "$CA_PLUGINS_ROOT"
cp "$SCRIPT_DIR"/fixtures/tasks/*.md "$CA_TASKS_ROOT"/
cp -r "$SCRIPT_DIR"/fixtures/skills/* "$CA_SKILLS_ROOT"/
cp -r "$SCRIPT_DIR"/fixtures/hooks/* "$CA_HOOKS_ROOT"/
cp -r "$SCRIPT_DIR"/fixtures/plugins/* "$CA_PLUGINS_ROOT"/
cp -r "$SCRIPT_DIR"/fixtures/prompts/* "$CA_PROMPTS_ROOT"/

# Seed a minimal config.json so GET /api/config behaves like an already-
# initialized install (200) rather than the legitimate-but-noisy 404 a
# genuinely fresh install returns (core/web/routers/config.py) — keeps
# every page's "no failed /api/* requests" check honest.
echo '{}' > "$CA_CONFIG_PATH"

# Fake claude/codex/gemini/opencode binaries ahead of anything real on PATH —
# see fixtures/fake-engines/README.md for why real CLIs must never run here.
export PATH="$SCRIPT_DIR/fixtures/fake-engines:$PATH"

PORT="${CA_E2E_PORT:-8798}"

echo "🧪 E2E scratch dir: $SCRATCH" >&2
echo "🚀 Starting CodeAgent backend on port $PORT (serving $FRONTEND_DIR/dist)..." >&2

# `exec` would replace this shell (and its trap) entirely, so cleanup would
# never run — run uvicorn as a background child instead and wait on it, so
# the EXIT/INT/TERM trap below still fires when Playwright stops the server.
cd "$REPO_ROOT"
uv run uvicorn core.web.server:app --host 127.0.0.1 --port "$PORT" &
SERVER_PID=$!

wait "$SERVER_PID"
