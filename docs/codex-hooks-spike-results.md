# Codex Hooks Spike Results

Live-tested against `codex-cli 0.142.5` on this dev machine before changing
`engines/start_codex.py`, following the same pre-build spike convention as
`docs/mcp-cli-spike-results.md`.

The spike was needed because CodeAgent was injecting hooks into
`.codex/settings.json` — a JSON file **codex never reads**. Codex hooks were
therefore entirely non-functional, and this was not merely a missing event-name
mapping.

## Method

`codex doctor` is not a usable validator here: it reports `config.toml parse
ok` even for a config containing a bogus field, because it checks TOML syntax
rather than the schema. The decisive check is the app-server's `hooks/list`
JSON-RPC method, which reports the hooks codex actually parsed for a given
cwd:

```jsonc
{"id":1,"method":"initialize","params":{"clientInfo":{"name":"s","version":"0"}}}
{"id":2,"method":"hooks/list","params":{"cwds":["<project>"]}}
```

Run it against an isolated `CODEX_HOME` so the real `~/.codex` is untouched.
Drive `bin/codex.exe` directly rather than the `codex.CMD` npm shim, which does
not propagate `kill()` and leaves the daemon running.

## Findings

**Hooks are enabled by default.** `codex features list` reports `hooks stable
true`.

**The config shape is Claude's, expressed in TOML.** Four candidate shapes were
tested; only the matcher-group form parsed:

| Shape | Result |
|---|---|
| `[[hooks.PreToolUse]]` with `type`/`command` inline | parsed, but yields **0 hooks** |
| `[hooks.PreToolUse]` as a table | error: `invalid type: map, expected a sequence` |
| `[[hooks.events.PreToolUse]]` | parsed, but yields **0 hooks** |
| matcher groups (below) | **1 hook** ✓ |

```toml
[[hooks.PreToolUse]]
matcher = "*"

[[hooks.PreToolUse.hooks]]
name = "branch-protection"
type = "command"
command = "python hook.py"
```

Read back as `eventName: "preToolUse"`, `handlerType: "command"`, `matcher:
"*"`, `timeoutSec: 600`.

**Event names match Claude's** — `PreToolUse`, `PostToolUse`, plus
`PermissionRequest`, `PreCompact`, `PostCompact`, `SessionStart`,
`UserPromptSubmit`, `SubagentStart`, `SubagentStop`, `Stop`.

**A `name` key is accepted but ignored.** It does not surface in hook metadata
and does not cause a parse error, so the existing injector's `name` field is
safe to keep.

**Both global and project-local config work.** `~/.codex/config.toml` and
`<project>/.codex/config.toml` were each confirmed to yield a parsed hook.

**Project-local hooks require project trust.** Without a trust entry codex
emits a `configWarning` and silently drops the project's hooks:

> Project-local config, hooks, and exec policies are disabled in the following
> folders until the project is trusted, but skills still load.

The entry lives in the *user-level* config:

```toml
[projects."E:\\path\\to\\project"]
trust_level = "trusted"
```

`CodexEngine.warn_if_project_untrusted()` prints this hint rather than editing
the user's global config automatically.

## Not covered

`hooks/list` proves codex *parses* the hooks. It does not prove they *fire* —
the parsed metadata reports `trustStatus: "untrusted"`, which suggests a
per-hook approval step on first execution. Confirming end-to-end execution
needs an authenticated codex session and was out of scope for this spike.
