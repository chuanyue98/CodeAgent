---
name: task-authoring
description: 协助用户编写高质量的 CodeAgent 自动化任务模板（Tasks）。
---

# Task Authoring (任务编排专家)

协助编写以后可以通过 `ca <engine> -t <name>`（如 `ca opencode -t <name>`、`ca claude -t <name>`）或 `ca batch-run <name> --engine <engine>` 重复调用的自动化剧本。

## Guidelines
1. **结构化要求**：生成的任务文件需以 `# <Title>` 作为一级标题（Web UI 读取首个 `# ` 标题与首个非标题正文行作为摘要），并包含以下四个二级标题板块：
   - `## Objective (目标)`（或 `## Objective`）
   - `## Context (背景)`（或 `## Context`）
   - `## Instructions (指令)`（或 `## Instructions`）
   - `## Verification (验证)`（或 `## Verification`）
   如需多阶段进度跟踪，可在二级标题下使用 `**目标**: ...` 与 `**状态**: [未开始|进行中|已完成]`（与 `TaskService` 解析规则一致）。
2. **位置与命名规范**：在 CodeAgent 的 `tasks/` 目录（若配置了 `CA_TASKS_ROOT` 或 `paths.resource_root` 则为其下 `tasks/`）创建 `<name>.md`；任务名 `<name>` 仅允许字母、数字、下划线、连字符和点号（匹配 `^[\w.-]+$`，不含路径分隔符）。
3. **精准指令**：Instructions 应具体、可操作，避免模糊描述，确保 AI 引擎能够准确执行。
4. **调用指引**：任务编写完成后，明确告知用户调用命令，例如 `ca opencode -t <name>` 或 `ca batch-run <name> --engine claude --dry-run`。

## Examples
- **动作**: 为“每日代码审计”创建一个新任务。
- **输出**: 在 `tasks/audit.md` 中生成包含标题、四个标准板块（Git 审计与 Lint 检查指令）的剧本，并提示使用 `ca opencode -t audit` 执行。
