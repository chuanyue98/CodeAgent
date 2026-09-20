# 跨引擎协作与任务委派 (Cross-Engine Delegation)

当前环境已内置 CodeAgent MCP 协作工具（包括 `ca_delegate_subtask`、`ca_handoff_session`）。

## 工具使用准则

1. **子任务委派 (`ca_delegate_subtask`)**：
   - 当用户明确要求由其他专项引擎处理任务时（例如：「让 Codex 补全单测/编写具体实现」、「让 Claude 攻坚复杂架构与核心设计」、「让 Antigravity 检索长篇文档」等），应主动调用 `ca_delegate_subtask` 工具进行委派。
   - 面对较大规模或适合拆分的工程任务时，你作为主模型负责全局规划与技术设计，将具备独立边界的模块实现、测试用例补全或代码迁移委派给对应引擎执行。
   - 工具默认在当前工作区直接就地修改代码（`isolate_worktree=False`），修改即刻生效，无需繁琐的分支切换；若需要完全隔离的沙盒实验，可显式传入 `isolate_worktree=True`。
   - 子任务执行完毕后，工具会返回执行状态、修改的文件列表及代码 Diff。请查验改动成果并向用户进行条理清晰的汇报。

2. **会话接力 (`ca_handoff_session`)**：
   - 当遇到当前引擎配额耗尽 (Rate Limit / 429)、不可逆的环境异常或陷入死循环时，可主动调用 `ca_handoff_session` 将会话上下文平滑移交给备用引擎继续服务。
