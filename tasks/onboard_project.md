# Onboard Project

Get a project that's new to CodeAgent into a working state: registered, bound to a sensible resource group, and documented.

## Objective

Leave the project registered in `config.json` under a resource group whose skills/prompts/hooks/plugins actually fit its stack, with a short note on what was chosen and why.

## Context

- Read `docs/configuration.md` for what a resource group and `project_registry` entry are before changing either.
- Prefer reusing an existing group (`common`, `work`, `web`, ...) over creating a new one unless the project's stack is genuinely distinct from every existing group.
- Do not invent skills/hooks/plugins that don't exist in `skills/`, `hooks/`, `plugins/` — only reference what `ca resources list` actually shows.

## Instructions

1. Inspect the target project: language(s), frameworks, build tooling, test runner, and whether it already has CI configured.
2. Run `ca resources list skills`, `ca resources list hooks`, and `ca resources list plugins` to see what's available to bind.
3. Decide whether an existing group fits or a new one is warranted; if new, name it after the project's actual domain, not generically.
4. Register the project (`project_registry` entry pointing at its path) bound to the chosen group.
5. Run `ca doctor` from inside the project directory to confirm the environment resolves cleanly.
6. Summarize what was bound and why in one short paragraph the next person can read without re-deriving the reasoning.

## Verification

`ca doctor` reports no unresolved skill/hook/plugin references for the project, `ca resources list skills --group <chosen group>` shows entries that plausibly apply to this project's stack, and the registration survives a fresh `ca` invocation from the project directory.
