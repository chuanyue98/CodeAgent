# Onboard Project

Get a project that's new to CodeAgent into a working state: registered, bound to a sensible resource group, and documented.

## Objective

Leave the project registered in `config.json` under a resource group whose skills/prompts/hooks/plugins actually fit its stack, with a short note on what was chosen and why.

## Context

- Read the configuration section of `README.md` for what a resource group and `project_registry` entry are before changing either.
- Prefer reusing an existing group configured in `config.json` (e.g. `common`, `codeagent`, or other existing groups) over creating a new one unless the project's stack is genuinely distinct from every existing group.
- Do not invent skills/prompts/hooks/plugins that don't exist in `skills/`, `prompt/`, `hooks/`, `plugins/` — only reference what `ca resources list` actually shows.

## Instructions

1. Inspect the target project: language(s), frameworks, build tooling, test runner, and whether it already has CI configured.
2. Ensure `config.json` exists (run `ca doctor --fix` if needed to seed it from `config.example.json`), then run `ca resources list skills`, `ca resources list prompts`, `ca resources list hooks`, and `ca resources list plugins` to see what's available to bind (pass `--group <name>` to inspect an existing group).
3. Decide whether an existing group fits or a new one is warranted; if new, define it under `groups` in `config.json` and name it after the project's actual domain, not generically.
4. Register the project bound to the chosen group using `ca project add <path> --group <chosen-group>` (or add a `project_registry` entry in `config.json`).
5. Run `ca doctor` from inside the project directory to confirm the environment and group resources resolve cleanly.
6. Summarize what was bound and why in one short paragraph the next person can read without re-deriving the reasoning.

## Verification

`ca project list` shows the project mapped to `<chosen-group>`, `ca doctor` reports `<chosen-group>` as the active group with no unresolved skill/hook/plugin references for the project, `ca resources list skills --group <chosen-group>` shows entries that plausibly apply to this project's stack, and the registration survives a fresh `ca` invocation from the project directory.
