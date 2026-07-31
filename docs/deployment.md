# Deployment

CodeAgent runs natively on your host by default (see the main [README](../README.md) —
`pip install -e .` / `uv sync`, then `ca ui`). This guide is for the alternative case: you
want to run the Web UI dashboard in a container, for example on a shared machine or a small
server. Everything here is based on the `Dockerfile` and `docker-compose.dev.yml` that ship
in the repository root — there is no separate "production" Dockerfile or compose file today.

## What the image runs

The `Dockerfile`:

- Is based on `python:3.13-slim`, installs `build-essential`, `curl`, and `git`, and installs
  Python dependencies with `uv sync --frozen --no-dev`.
- Copies only the runtime pieces CodeAgent needs to launch engines and serve the dashboard:
  `core/`, `engines/`, `prompt/`, `skills/`, `hooks/`, `plugins/`, `tasks/`, and
  `ca_launcher.py`, plus a pre-built `web/frontend/dist/`.
- Does **not** copy `config.json` into the image — you need to supply it yourself (bind mount
  or `docker cp`) or the app will fall back to whatever defaults `ca doctor`/first-run would
  otherwise create.
- `EXPOSE`s port `8524` and sets `CMD ["python", "ca_launcher.py", "ui"]`, so the container's
  default action is to start the Web UI/API server.
- Sets `ENV CA_UI_HOST=0.0.0.0` (see below for what this controls).

### Build the frontend before building the image

The Dockerfile's `COPY web/frontend/dist/ web/frontend/dist/` step requires that directory to
already exist — it is not built inside the container. Build it first:

```bash
cd web/frontend && bun install && bun run build   # or: npm install && npm run build
cd ../..
docker build -t codeagent .
```

The project's own CI (`.github/workflows/ci.yml`, job "Package — Docker image") does the same
thing: it builds the frontend first, drops the resulting `dist/` into place, then runs
`docker build -t codeagent:ci .` as a build sanity check. That job does not push or publish
the image anywhere, so there is currently no pre-built image to `docker pull` — you build it
yourself from source.

### Run it directly

```bash
docker run -d \
  --name codeagent \
  -p 8524:8524 \
  -v "$(pwd)/config.json:/app/config.json" \
  -v "$HOME/.ca_analytics_history.jsonl:/root/.ca_analytics_history.jsonl" \
  -v "$(pwd)/.ca_task_logs:/app/.ca_task_logs" \
  -v "$HOME/.claude:/root/.claude" \
  -v "$HOME/.codex:/root/.codex" \
  -v "$HOME/.gemini:/root/.gemini" \
  -v "$HOME/.opencode:/root/.config/opencode" \
  codeagent
```

(Adjust the auth-directory mounts to whichever engine CLIs you actually use — see
[Persistent state](#persistent-state) below.)

## `docker-compose.dev.yml`

For local iteration, the repo ships `docker-compose.dev.yml`. As the filename says, it's a
dev-oriented compose file — it bind-mounts `core/`, `engines/`, `ca_launcher.py`, and
`config.json` from the host into the container for live code reloading, on top of the same
port mapping and persistent-state mounts described below:

```bash
docker compose -f docker-compose.dev.yml up --build
```

It also sets `CA_DEBUG=1` and `restart: unless-stopped`. If you want an immutable,
non-live-reloading container, use `docker run` against the built image directly (previous
section) rather than this compose file, since it intentionally overlays your working tree on
top of the image's copy of `core/`/`engines/`.

## `CA_UI_HOST`

`ca_launcher.py`'s `ui` command binds the FastAPI/uvicorn server to
`os.environ.get("CA_UI_HOST", "127.0.0.1")` — i.e. it listens on loopback only unless
`CA_UI_HOST` is set. Inside a container this matters: binding to `127.0.0.1` would make the
server unreachable through the container's published port, since traffic arriving via Docker's
port mapping doesn't originate from `127.0.0.1` inside the container's network namespace. The
`Dockerfile` sets `CA_UI_HOST=0.0.0.0` for exactly this reason, so the server accepts
connections on all interfaces inside the container. The dashboard listens on port `8524`
(`UI_API_PORT` in `ca_launcher.py`), which is what both the `Dockerfile`'s `EXPOSE` and
`docker-compose.dev.yml`'s port mapping use.

If you run CodeAgent natively on a host (no container) and want the dashboard reachable from
other machines, the same `CA_UI_HOST=0.0.0.0 ca ui` override applies — just be aware this
removes the loopback-only default and exposes the dashboard to your network.

## Web UI authentication

The API is not safe to expose unauthenticated: a caller can register a workspace and open a
PTY running a provider CLI with your credentials. `core/web/security.py` applies three checks
to every `/api` route (static assets and `/api/health` stay open so the browser can load the
app and so readiness probes work):

- **`Host` header** must name this server. Blocks DNS rebinding, which defeats a
  bind-address check.
- **`Origin`**, when present, must be loopback or match `Host`. Blocks drive-by WebSocket
  hijacking — a WebSocket handshake is *not* subject to the same-origin policy, so without
  this any page you visit could open `ws://127.0.0.1:8524/api/pty/ws` and drive a shell.
- **Token**, from the `X-CA-Token` header or a `ca_token` query parameter (the query form
  exists because `EventSource` and `WebSocket` cannot set headers).

`ca ui` generates the token at `~/.codeagent/ui-token` and opens the browser with it in the
URL; the app stores it in `sessionStorage` and strips it from the address bar. To open the UI
manually, get the value with `ca ui --show-token`.

### In a container

Behind Docker's port mapping the `Host` your users send is whatever they typed, and the
container's own `Host` expectations differ from a native install. Two options:

```bash
# Reachable as http://codeagent.internal:8524
CA_UI_ALLOWED_HOSTS=codeagent.internal CA_UI_TOKEN=<a-long-random-secret> ca ui

# Behind a reverse proxy that already authenticates AND validates Host
CA_UI_AUTH=off CA_UI_ALLOWED_HOSTS='*' ca ui
```

Set `CA_UI_TOKEN` explicitly for containers — a generated token inside an ephemeral
filesystem changes on every restart. Do not use `CA_UI_AUTH=off` without something in front
doing authentication: it leaves shell access on the machine open to anything that can reach
the port.

## Persistent state

CodeAgent writes state to a handful of paths outside its own source tree. Mount these as
volumes if you want that state to survive a container restart/rebuild:

| Path (as used in code) | Location relative to | What it is |
|---|---|---|
| `config.json` | app root (`/app`) | Project configuration; not baked into the image, must be supplied |
| `.ca_analytics_history.jsonl` | `$HOME` (`core/analytics/history.py`) | Usage/cost analytics history read by the dashboard |
| `.ca_task_logs/` | app root (`core/services/runner_service.py`, `core/web/routers/logs.py`) | Background task run logs, status DB (`runs.db`) |
| `.codeagent/agent-gateway.sqlite3` | `$HOME` (`core/web/server.py`) | Agent gateway state database |

Inside the container `$HOME` is `/root` (the image runs as root), which is why
`docker-compose.dev.yml` mounts `./.ca_analytics_history.jsonl` to
`/root/.ca_analytics_history.jsonl` and `./.codeagent-home` to `/root/.codeagent`.

### Provider CLI authentication

CodeAgent drives the official `claude`/`gemini`/`codex`/`opencode` CLIs rather than talking to
any provider API directly, and does not manage their login/session storage itself — that's
each CLI's own concern. `docker-compose.dev.yml` mounts the corresponding host directories
into the container (`.claude` → `/root/.claude`, `.codex` → `/root/.codex`, `.gemini` →
`/root/.gemini`, `.opencode` → `/root/.config/opencode`) so a container can reuse credentials
from a host that's already logged in to those CLIs. Note this is separate from CodeAgent's own
per-project artifacts under each engine's dotfolder (e.g. skill symlinks, injected
`settings.json`) — for the Claude and OpenCode engines those are written relative to the
current working directory (`engines/start_claude_code.py`, `engines/start_opencode.py`), while
Gemini and Codex resolve their plugin-link directories under `$HOME`
(`engines/start_gemini.py`, `engines/start_codex.py`). The precise on-disk format each vendor
CLI uses for its own login/session tokens is outside this repository's code and has not been
independently verified here — treat the mounts above as "reuse whatever the host CLI already
has," not as a guarantee of every file each CLI might need.

## Caveats

- There is no published/hosted CodeAgent image — build it from source as shown above.
- There is only one Dockerfile and one compose file in the repo today
  (`docker-compose.dev.yml`); nothing here has been tuned for multi-user production hardening
  (e.g. reverse proxy, TLS termination, non-root container user) — add those yourself if you
  need them.
