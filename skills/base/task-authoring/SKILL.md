---
name: task-authoring
description: 协助用户编写高质量的 CodeAgent 自动化任务模板（Tasks）。
---

# Task Authoring (任务编排专家)

协助编写以后可以通过 `ca -t <name>` 重复调用的自动化剧本。

## Guidelines
1. **结构化要求**：生成的任务文件必须包含 Objective (目标), Context (背景), Instructions (指令), Verification (验证) 四个板块。
2. **位置规范**：在 CodeAgent 的 `tasks/` 目录下创建并实时维护指定的 `.md` 文件。
3. **精准指令**：Instructions 应具体、可操作，避免模糊描述，确保 AI 引擎能够准确执行。
4. **调用指引**：任务编写完成后，明确告知用户调用命令。

## Examples
- **动作**: 为“每日代码审计”创建一个新任务。
- **输出**: 在 `tasks/audit.md` 中生成包含 Git 审计和 Lint 检查的剧本。
