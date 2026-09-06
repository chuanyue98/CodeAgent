# Task 4: 全量回归与 Phase 1 验收报告

## 1. 任务概述
- **任务编号**: Task 4
- **目标**: 执行 CodeAgent Phase 1（AUDIT-001, AUDIT-002, AUDIT-003）全量测试回归与代码规范检查，归档审计报告与架构文档更新，并创建 Phase 1 里程碑交付提交。

## 2. Phase 1 核心成果回顾
1. **AUDIT-002: 单源 Engine Registry 收敛**
   - 建立 `core/engine_registry.py` 作为引擎声明的唯一真实来源（Single Source of Truth）。
   - 收敛 `ca_launcher.py`、`engines/start_*.py`、`core/doctor.py`、`core/task_runner.py` 与批量运行 CLI 中的引擎定义。
   - 彻底消除了引擎配置漂移与重复定义风险。
2. **AUDIT-001: Agent Gateway 默认关闭与实验性隔离**
   - Agent Gateway（包含 supervisor、worker、session 等服务）标记为实验性特性。
   - 默认状态下关闭（未授权不得启动未受控执行服务），提供配置项 `features.experimental_agent_gateway` 及环境变量 `CODEAGENT_ENABLE_EXPERIMENTAL_GATEWAY=1` 控制启用。
3. **AUDIT-003: Codex 安全姿态默认收敛**
   - 治理交互模式下的安全姿态，默认在沙箱中运行并开启审批，彻底移除全局默认 `--dangerously-bypass-approvals-and-sandbox`。
   - 仅在显式传入 `--yolo` 标志或设置 `CA_YOLO=1` 时开启免审批模式。

## 3. 全量回归与验证结果

### 3.1 全量测试套件
```bash
uv run pytest
```
**执行结果**：
```text
====================== 1080 passed, 11 skipped in 55.21s =======================
```
- 测试用例总数：1091
- 通过数：1080
- 跳过数：11（符合预期，包含依赖特定本地 CLI/环境的可选外部集成测试）
- 失败数：0
- 错误数：0

### 3.2 代码风格与规范检查 (Ruff)
```bash
uv run ruff check .
```
**执行结果**：
```text
All checks passed!
```
- 0 lint errors, 0 warnings.

## 4. 交付物归档
- **架构文档同步**：更新 `docs/architecture.md`，同步记录 Codex 默认沙箱审批安全策略以及 Agent Gateway 实验性环境变量控制。
- **审计报告归档**：将《CodeAgent — 全仓库工程审计与竞品对标报告》`audit-report.html` 正式纳入版本管理，作为架构演进与治理依据。
- **里程碑提交**：`chore: Phase 1 安全治理与注册表收敛全量验收通过`。
