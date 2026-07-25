# Create PR

Turn the current branch's work into a reviewable pull request.

## Objective

Commit the outstanding work on a suitable branch, push it, and open a pull request whose description tells a reviewer what changed and why.

## Context

- Use the `gh` CLI for GitHub operations. If it is not authenticated, stop and say so rather than guessing an alternative.
- Never commit or push directly to the default branch. If the current branch is the default one, create a topic branch first.
- Read the repository's recent commit messages and follow their conventions.

## Instructions

1. Run `git status` and `git diff` and confirm every change belongs in this PR. Leave unrelated edits out.
2. Branch if needed, then stage and commit with a message that says what changed and why, not just which files moved.
3. Push the branch and open the PR with `gh pr create`.
4. Write the body as: the problem, the change, and how it was verified. Link any issue it closes.
5. Report the PR URL.

## Verification

`gh pr view` shows an open PR on a non-default branch, the diff matches what was intended, and the description would let a reviewer start without asking a follow-up question.
