# Fake engine CLIs

Stand-ins for `claude`/`codex`/`opencode`, prepended onto `PATH` for
the E2E backend process only (see `../../start-server.sh`). None of these
CLIs are installed on CI runners, and even locally, calling the real ones
would hit paid APIs, need interactive auth, and be flaky — the same
reasoning behind `tests/test_chat_service.py`'s `_write_fake_cli()` and
`tests/test_mcp_service.py`'s fake-binary fixtures in the Python test suite;
this is that same technique, just as long-lived scripts instead of per-test
temp files.

All four files have identical content (engine is auto-detected from
`argv[0]`'s basename) — edit one, then re-copy to the other three:

```
cp claude codex opencode
```

Handles three argv shapes, matching real invocations built by
`core/services/mcp_service.py` and `engines/start_*.py`:
1. `mcp add ...` — writes into the engine's real native config file format
   (`.mcp.json`, `~/.codex/config.toml`,
   `~/.config/opencode/opencode.json`) so a subsequent real
   `mcp_service.list_servers()` call sees it — only the CLI binary is fake,
   the read path is real production code.
2. `mcp remove <name>` — only for claude/codex (the only two engines
   `mcp_service.py` actually shells out to for removal; opencode
   removal edits their config file directly and never invokes the CLI).
3. Any invocation containing a structured-output flag
   (`--output-format`/`--json`/`-o`/`--format`) — emits each engine's real
   stream-json/JSONL event shape with a fake reply and session id, so
   ChatPage's real SSE-consuming code has something to parse.

Anything else (the plain `ca_launcher.py`-driven task-run invocation, used
by Dashboard/Cron) falls through to printing one line and exiting 0.
