# ChatPage CLI Spike Results

Before writing any ChatPage code, each of the four wrapped CLIs was
exercised manually with a real two-turn exchange, where turn 2 asks the
engine to recall turn 1's exact content — the only way to confirm
"resume" actually carries prior context forward rather than just
accepting a `--resume`-shaped flag that quietly starts a fresh session.

## claude — confirmed

```
claude -p --output-format stream-json --include-partial-messages --verbose \
  --dangerously-skip-permissions "say hello and nothing else"
# -> session_id in every stream-json line, e.g. 028e2164-241e-4a10-9daa-df13b5787a90

claude -p --output-format stream-json --include-partial-messages --verbose \
  --dangerously-skip-permissions -r 028e2164-241e-4a10-9daa-df13b5787a90 \
  "what did I just ask you to say?"
# -> "say hello and nothing else" (verbatim recall, same session_id)
```

`--output-format stream-json` requires `--verbose` when combined with `-p`
(the CLI errors out otherwise — not documented in `--help`).

## codex — confirmed

```
codex exec --json --dangerously-bypass-approvals-and-sandbox \
  "say hello and nothing else"
# -> {"type":"thread.started","thread_id":"019f5103-5856-7b02-acfa-38b937882294"}

codex exec resume 019f5103-5856-7b02-acfa-38b937882294 --json \
  --dangerously-bypass-approvals-and-sandbox "what did I just ask you to say?"
# -> "You asked me to say hello." (same thread_id)
```

The session identifier is `thread_id`, not `session_id`, in the JSON event
stream.

## opencode — confirmed

```
opencode run "say hello and nothing else" --format json --auto
# -> sessionID: ses_0aefac720ffeXwqJhu5uCdPd5Y

opencode run "what did I just ask you to say?" --format json --auto \
  -s ses_0aefac720ffeXwqJhu5uCdPd5Y
# -> "You asked me to say hello" (same sessionID)
```

`--auto` ("auto-approve permissions that are not explicitly denied") is
opencode's skip-approval flag — this wasn't in `--help` output cited by the
original design doc and had to be found by re-reading `opencode run --help`.

