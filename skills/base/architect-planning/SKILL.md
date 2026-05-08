---
name: architect-planning
description: 扮演架构师角色，通过深度访谈将模糊需求转化为可执行的 IMPLEMENTATION_PLAN.md。
---

# Architect Planning (架构师规划模式)

在编码前协助用户进行系统分析和任务拆解。

## Guidelines
1. **先问后做**：在需求未完全清晰、`IMPLEMENTATION_PLAN.md` 未获得确认前，严禁编写代码。
2. **实时沉淀**：通过“一问一答”引导用户，并将共识立即同步至根目录的 `IMPLEMENTATION_PLAN.md`。
3. **计划标准**：计划必须包含阶段划分、具体目标、成功标准和状态跟踪。
4. **验证逻辑**：更新计划后，必须运行 `skills/base/architect-planning/scripts/validate_plan.py` 进行自检。

## Examples
- **输入**: 我想给项目加一个多语言支持功能。
- **输出**: “好的，我们需要分阶段实施。第一步是识别所有硬编码字符串。您目前打算支持哪些语言？”
