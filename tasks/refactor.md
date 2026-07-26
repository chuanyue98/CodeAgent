# Refactor

Improve the structure of a module without changing what it does.

## Objective

Restructure the code the user names — or, if they name nothing, the largest file in the area they are working in — so it is easier to follow, while keeping observable behaviour identical.

## Context

- Behaviour-preserving only. If you find a bug on the way, report it; do not fix it in the same pass.
- The test suite is the contract. Find how to run it (`pytest`, `npm test`, and so on) before you change anything.
- Match the surrounding code's conventions rather than importing your own.

## Instructions

1. Run the existing tests first and record that they pass. A refactor that starts from a red suite proves nothing.
2. Describe the current structure and name the specific problem — duplication, a function doing several jobs, a leaky abstraction — before editing.
3. Make the change in small steps, re-running the tests after each one.
4. Do not add features, change public signatures, or reformat untouched code.
5. Summarise what moved where, and why the new shape is easier to work with.

## Verification

The test suite passes exactly as it did before the refactor, no public API changed, and the diff contains no unrelated formatting churn.
