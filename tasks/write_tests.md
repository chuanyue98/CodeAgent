# Write Tests

Fill in missing test coverage for the code the user points at, or for the current diff if they name nothing.

## Objective

Add tests that would catch a real regression in the target code — not tests that merely execute lines for coverage's sake.

## Context

- Find and reuse the project's existing test framework and conventions; do not introduce a second one.
- Prefer testing through the public interface over reaching into internals.
- If the target code is untestable as written (hidden global state, unmockable I/O baked in), say so and propose the smallest seam that would fix it — do not restructure it unasked.

## Instructions

1. Read the target code and enumerate its behaviors: the happy path, each documented edge case, and each error condition it's responsible for handling.
2. Check what's already covered by running the existing suite with coverage, or by reading nearby test files — do not duplicate tests that already exist.
3. Write one test per behavior, named so a failure explains itself without opening the test body.
4. Cover the edges that are actually reachable: empty/null input, boundary values, concurrent or repeated calls if the code is stateful — skip edge cases the type system or caller already makes impossible.
5. Run the new tests and confirm each one fails if you comment out the logic it targets — a test that can't fail proves nothing.

## Verification

The full suite passes, every new test fails when its corresponding logic is broken (verified by a temporary local mutation), and no test depends on execution order or leftover state from another test.
