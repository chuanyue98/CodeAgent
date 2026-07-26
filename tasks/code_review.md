# Code Review

Review the working changes on the current branch and report what a careful reviewer would flag.

## Objective

Produce a focused review of the uncommitted and unpushed changes in this repository — correctness first, then clarity. Do not rewrite the code; report.

## Context

- Run `git status` and `git diff` (plus `git diff --staged`) to see the working changes.
- If the branch is clean, compare against the default branch instead: `git diff origin/HEAD...HEAD`.
- Respect the standards injected from this project's prompt group; they take precedence over generic style preferences.

## Instructions

1. Read the full diff before commenting on any single hunk — a change that looks wrong in isolation is often correct in context.
2. For each finding, state the file and line, what breaks, and the concrete input or state that triggers it.
3. Rank findings: correctness and data loss first, then security, then performance, then readability.
4. Call out missing test coverage for any behaviour the diff introduces or changes.
5. Say explicitly when you find nothing wrong in a file rather than inventing minor nits.

## Verification

The review names real files and lines that exist in the diff, and every claimed defect comes with a scenario that would actually reproduce it.
