# Fix Bug

Diagnose a specific failure — a stack trace, an error message, or a described symptom — and fix its root cause.

## Objective

Turn a reported symptom into a confirmed root cause and a minimal fix, with a test that proves the bug is gone and stays gone.

## Context

- Start from what was actually given: a stack trace, log output, a failing test, or a plain-language description. If none of that was provided, ask for it or reproduce the failure yourself before touching any code.
- A stack trace's top frame is a symptom location, not necessarily the cause — trace the value or state backward until you find where it first went wrong.
- Do not fix the first suspicious-looking thing you see; confirm the mechanism before changing code.

## Instructions

1. Reproduce the failure locally (a failing test, a script, or the exact repro steps given). If it can't be reproduced, say so rather than guessing at a fix.
2. Read the trace/error bottom-up if it's a stack trace, or trace the relevant data flow top-down if it's a described symptom, until you find the exact line and condition that causes the wrong behavior.
3. State the root cause in one sentence — the specific input or state combination that triggers it — before writing any fix.
4. Write the smallest change that fixes the root cause. Do not refactor surrounding code or fix unrelated issues you notice along the way; report those separately instead.
5. Add a regression test that fails on the old code and passes on the fix.

## Verification

The regression test fails against a stash/revert of the fix and passes with it applied, the full existing suite still passes, and the fix touches only the code needed to address the root cause.
