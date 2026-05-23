#!/usr/bin/env bash
input=$(cat)
printf '%s' "$input" | grep -q '"tool_name":[[:space:]]*"Bash"' || exit 0
printf '%s' "$input" | grep -q 'git commit' || exit 0

if ! uv run ruff check . 1>&2; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"ruff check 未通过，请修复后再提交"}}'
    exit 0
fi

if ! uv run ruff format --check . 1>&2; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"ruff format 未通过，请运行 uv run ruff format . 格式化后再提交"}}'
    exit 0
fi
