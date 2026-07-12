# Playwright E2E test suite — design notes & status

Branch: `feat/e2e-tests` (off `main`, not yet committed).

## Why

Correctness beyond unit tests had relied on ad-hoc manual Playwright driving
during each feature's development (Audit Trail, ChatPage, CronPage, MCP
management) — real, but not repeatable, and not run in CI. The existing
`vitest`/`jsdom` suite (`web/frontend/src/**/*.test.tsx`) is component-level
with a mocked `fetch` — it never exercises a real backend or a real browser.

Scope, as confirmed with the user: **smoke coverage on every one of the 15
routed pages + deep interaction coverage on the highest-value stateful
pages** (Chat, Cron, MCP, Configuration, one representative gallery
[Skills], Dashboard), plus basic UI/UX checks (accessibility, console/network
hygiene, sidebar-collapse layout) layered onto the smoke tier.

## Design

### Isolation: `$HOME` override, not just the app's own `CA_*_ROOT` vars

The Python test suite already isolates itself via `CA_CONFIG_PATH`,
`CA_TASKS_ROOT`, `CA_SKILLS_ROOT`, `CA_PROMPTS_ROOT`, `CA_HOOKS_ROOT`,
`CA_PLUGINS_ROOT`. But `core/services/mcp_service.py`'s codex/opencode paths
(`Path.home() / ".codex" / "config.toml"`, `Path.home() / ".config" /
"opencode" / "opencode.json"`) and the session-history parsers read
`Path.home()` directly — not env-var-overridable. `web/frontend/e2e/start-server.sh`
therefore overrides `$HOME` itself to a scratch temp dir, which neutralizes
all of these at once with zero code changes elsewhere. This is a stronger
guarantee than the manual cleanup discipline used during Cron/MCP's manual
verification earlier in this project's history.

**Known gap, not yet handled**: `core/services/runner_service.py`'s
`TaskRunner` singleton in `core/web/routers/tasks.py` hardcodes its log
directory to `ROOT_DIR / ".ca_task_logs"` — the *real* repo root, not
overridable via any `CA_*` env var. Any spec that triggers a real task run
(Dashboard's "Run", Cron's "Run now") will write a real (gitignored, but
real) log file into this repo's own `.ca_task_logs/`. Each such spec must
explicitly delete its own task-id-matching log file in teardown.

### Real backend, real browser, fake engine CLIs only

E2E tests run against a real `uvicorn core.web.server:app` process serving
the real production build (`vite build` → `dist/`) — single origin, no
vite-proxy port juggling. `claude`/`codex`/`gemini`/`opencode` are never
real: not installed on CI runners, and even locally would hit paid APIs,
need interactive auth, and be flaky. `web/frontend/e2e/fixtures/fake-engines/`
holds stand-in scripts (same technique as `tests/test_chat_service.py`'s
`_write_fake_cli()` / `tests/test_mcp_service.py`'s fake binaries, just
long-lived instead of per-test) prepended onto `PATH` for the E2E backend
process only. See that directory's own `README.md` for the exact argv
shapes handled.

### Directory layout

```
web/frontend/
  playwright.config.ts
  e2e/
    start-server.sh             # isolated launch: $HOME override, CA_*_ROOT, fake-engine PATH
    fixtures/
      fake-engines/{claude,codex,gemini,opencode}
      tasks/smoke-test.md
      skills/base/e2e-smoke-skill/SKILL.md
    smoke.spec.ts                # one test per page (all 15)
    chat.spec.ts                 # deep — not yet written
    cron.spec.ts                 # deep — not yet written
    mcp.spec.ts                  # deep — not yet written
    config.spec.ts               # deep — not yet written
    skills.spec.ts               # deep — not yet written
    dashboard.spec.ts            # deep — not yet written
```

## Status (paused here, resume in this order)

**Done:**
- `@playwright/test` + `@axe-core/playwright` installed; chromium confirmed working.
- Fake-engine CLIs written and hand-verified against the real `mcp_service.py` read path for all 4 engines (round-trips add/remove correctly). Caught and fixed two real bugs during testing: an argv off-by-one (`args[1:]` vs `args[2:]`), and a message-position bug (gemini/opencode's message isn't the last arg, unlike claude/codex).
- `start-server.sh` written and hand-verified: scratch dir created on start, `$HOME`-isolated (confirmed `GET /api/mcp/codex` returns `[]` against the scratch home, not the real `~/.codex/config.toml`), fully cleaned up on `SIGTERM` (fixed a bug where `exec uv run uvicorn` replaced the trap-owning shell and silently disabled cleanup — now backgrounds uvicorn and `wait`s so the trap fires).
- `playwright.config.ts`, `.gitignore` entries, `package.json` scripts (`e2e`, `e2e:report`) all in place.
- Harness sanity-checked end-to-end with a throwaway spec (since deleted).
- `e2e/smoke.spec.ts` written and run. **First real run: 7/15 passed, 8 failed** — the suite is correctly catching real, pre-existing accessibility issues, not a suite bug. Chat, Skills, Prompts, Configuration, Cron, Analytics, Sessions, and Audit Trail each have at least one "serious"/"critical" axe violation. The one fully inspected so far: an unlabeled `<input type="date">`, likely from a shared date-range-filter component reused across several of those pages. The other 7 pages' exact violations weren't pulled before pausing.

**Remaining, in order:**
1. Pull the full a11y violation list for all 8 failing pages (`npx playwright test smoke.spec.ts --reporter=list`, or `npx playwright show-report`, or read each `test-results/*/error-context.md`). If it's mostly the one shared-component root cause, fix it now (small, contained). If the failures span genuinely unrelated issues across many components, stop and ask the user whether to fix now or file as follow-up + loosen the assertion for those pages meanwhile — don't silently downgrade the check without deciding this explicitly.
2. Write the six deep interaction specs (`chat.spec.ts`, `cron.spec.ts`, `mcp.spec.ts`, `config.spec.ts`, `skills.spec.ts`, `dashboard.spec.ts`), each handling the `.ca_task_logs/` cleanup gap above where relevant (dashboard/cron).
3. Wire a new `e2e` job into `.github/workflows/ci.yml` (`needs: [backend, frontend]`; `uv` + Bun + `playwright install --with-deps chromium`; `npx playwright test`; upload `playwright-report/` on failure).
4. Full local run — confirm `git status` clean before/after against the real `~/.codex`, `~/.config/opencode`, `~/.claude`, and this repo's own `config.json`/`tasks/`/`.ca_task_logs/`; one intentional-break sanity check; push and confirm the CI `e2e` job passes.
5. Commit (this branch has zero commits so far), push, open PR, follow the established review-fix cycle used for every prior phase.
