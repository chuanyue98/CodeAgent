# MCP CLI Spike Results

Live-tested (not just `--help`) on this dev machine before writing
`core/services/mcp_service.py`, per the Phase D mandatory pre-build spike in
the CronPage/MCP plan. Each engine was tested from a scratch project
directory outside this repo: `add` a local/stdio server, inspect the
resulting config file, `list`, then attempt `remove`.

## claude

- `claude mcp add --scope project <name> -- <cmd> [args...]` writes to
  `<project>/.mcp.json`:
  ```json
  {"mcpServers": {"<name>": {"type": "stdio", "command": "<cmd>", "args": [...], "env": {}}}}
  ```
- `claude mcp remove <name>` works correctly (confirmed: entry removed from
  `.mcp.json`).
- `claude mcp list` mixes in account-level MCP connectors (Google Drive,
  Gmail, etc. in this account) alongside project entries — **do not** parse
  `list`'s text output for project server state; read `.mcp.json` directly
  instead.

## codex

- `codex mcp add <name> --env KEY=VALUE -- <cmd> [args...]` writes to the
  **global** `~/.codex/config.toml` under `[mcp_servers.<name>]`, regardless
  of cwd — the CLI itself prints "Added **global** MCP server". Codex has no
  project-scoping concept for MCP servers in this version.
- `codex mcp remove <name>` works correctly.
- `codex mcp list --json` returns clean structured JSON — usable directly if
  ever needed, though `mcp_service.py` reads `config.toml` via `tomlkit` for
  consistency with `engines/start_codex.py`'s existing load/save pattern.

## gemini

- `gemini mcp add --scope project <name> <cmdOrUrl> [args...]` writes to
  `<project>/.gemini/settings.json`:
  ```json
  {"mcpServers": {"<name>": {"command": "<cmd>", "args": [...]}}}
  ```
- **`gemini mcp remove --scope project <name>` reproducibly fails** with
  `Server "<name>" not found in project settings.` — confirmed on a fresh
  directory, immediately after a successful `add`, twice. This is a CLI
  defect/limitation in this environment, not a scope or trust-folder issue
  (the "untrusted folder" warning shown by `mcp list` is unrelated — it only
  affects whether servers are *enabled*, not whether `remove` can find them).
  **v1 fallback**: `mcp_service.py` removes gemini servers by directly
  editing `.gemini/settings.json`'s `mcpServers` key (pop the entry, atomic
  write, preserve every other key) rather than shelling out.

## opencode

- `opencode mcp add <name> --env KEY=VALUE -- <cmd> [args...]` (or `--url`
  for remote) **writes to the global** `~/.config/opencode/opencode.json`
  under a top-level `mcp` key, regardless of cwd — no project-scope flag
  exists in `--help`. Format observed:
  ```json
  {"mcp": {"<name>": {"type": "local", "command": ["<cmd>", "arg1", ...], "environment": {"KEY": "VALUE"}}}}
  ```
  Note the key is `environment`, not `env`, and `command` is a single array
  (program + args combined), unlike the other three engines.
- **There is no `opencode mcp remove` subcommand at all** — `opencode mcp
  --help` only lists `add|list|auth|logout|debug`; `logout` only clears
  OAuth credentials, not the server entry. **v1 fallback**: `mcp_service.py`
  removes opencode servers by directly editing
  `~/.config/opencode/opencode.json`'s `mcp` key (pop the entry, atomic
  write, preserve every other key — verified live that `opencode mcp list`
  correctly reflects a hand-edited removal).

## Summary for `mcp_service.py`

| Engine | Scope | Add/Remove mechanism |
|---|---|---|
| claude | per-project (`.mcp.json`) | both via CLI |
| codex | global (`~/.codex/config.toml`) | both via CLI |
| gemini | per-project (`.gemini/settings.json`) | add via CLI, remove via direct file edit (CLI broken) |
| opencode | global (`~/.config/opencode/opencode.json`) | add via CLI, remove via direct file edit (CLI lacks the subcommand) |

All four engines' `list_servers()` reads go **directly against the native
config file**, not CLI text output, for consistency and because `claude mcp
list`/`gemini mcp list` output isn't cleanly machine-parseable (health
status text, account-level entries mixed in, etc).
