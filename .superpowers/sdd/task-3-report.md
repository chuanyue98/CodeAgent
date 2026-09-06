# Task 3: Codex 交互模式安全姿态治理 (AUDIT-003) 实施报告

## 1. 任务概述
- **任务编号**: Task 3 (AUDIT-003)
- **目标**: 治理 Codex 交互模式下的安全姿态，默认启用沙箱与审批，取消默认全局免审批；仅在显式声明 `--yolo` 或 `CA_YOLO=1` 时注入 `--dangerously-bypass-approvals-and-sandbox`。

## 2. 变更详情

### 2.1 引擎层 (`engines/start_codex.py`)
- **`CodexEngine.build_command`**:
  - 方法签名更新为 `build_command(self, message: str = "", non_interactive: bool = False, yolo: bool = False) -> list[str]`。
  - 在交互模式下（`non_interactive=False`），默认不注入 `--dangerously-bypass-approvals-and-sandbox`。
  - 当 `yolo=True`、`getattr(self, "yolo", False)` 为真或环境变量 `CA_YOLO` 为 `1`/`true` 时注入 bypass 参数。
  - 在非交互模式下（`non_interactive=True`），维持自动执行能力，包含 exec 和 bypass 参数。
- **`CodexEngine.build_interactive_command`**:
  - 新增辅助方法，便于按姿态构建交互命令。
- **参数解析与调用**:
  - `parse_arguments()` 中 `-y / --yolo` 参数默认值改为 `default=False`，帮助文案使用 `cli.help.yolo_mode`。
  - 在调用 `engine.build_command(...)` 时显式传入 `yolo=args.yolo`。

### 2.2 CLI 启动入口与辅助模块
- **`core/cli/main.py`**:
  - click option `-y / --yolo` 默认值改为 `default=False`，帮助说明更新为 `Enable YOLO mode (bypass sandbox and approvals)`。
- **`core/cli/helpers.py`**:
  - 取消对 `extra_params` 无条件追加 `"-y"` 的逻辑。
  - 仅在 `obj.get("yolo", False)` 为 True 时，向 `extra_params` 追加 `"-y"`。
  - 仅在启用 YOLO 或命令行传入 `"-y"`/`"--yolo"` 时打印 YOLO 模式安全警告。

### 2.3 国际化文案 (`core/i18n.py`)
- 增加 `cli.help.yolo_mode`:
  - `en`: `"YOLO mode (bypass approvals/sandbox)"`
  - `zh`: `"开启 YOLO 模式 (跳过审批与沙箱)"`
- 保留原有 `cli.help.yolo_default_on`，确保对其他旧引擎调用的向后兼容性。

### 2.4 测试用例 (`tests/test_codex_adapter.py` & `tests/test_ca_launcher.py`)
- **`tests/test_codex_adapter.py`**:
  - `test_codex_default_does_not_bypass_sandbox`: 验证默认交互模式无 bypass 标志。
  - `test_codex_yolo_explicitly_bypasses_sandbox`: 验证显式 `yolo=True` 注入 bypass 标志。
  - `test_codex_build_command_default_interactive_no_bypass`: 验证带 prompt 默认交互模式无 bypass。
  - `test_codex_build_command_yolo_true_bypasses`: 验证 `yolo=True` 包含 bypass 且包含 prompt。
  - `test_codex_build_command_ca_yolo_env_bypasses`: 验证 `CA_YOLO=1` 环境变量触发 bypass。
  - `test_codex_build_command_non_interactive_bypasses`: 验证非交互模式仍然包含 exec 与 bypass。
- **`tests/test_ca_launcher.py`**:
  - 更新因默认不再追加 `"-y"` 导致的断言，新增 `test_main_engine_selection_with_yolo` 与 `test_yolo_flag_defaults_to_false`，全面覆盖安全模式与 YOLO 模式。

## 3. 验证结果

### 3.1 针对性测试
```bash
uv run pytest tests/test_codex_adapter.py tests/test_codex_engine_hooks.py tests/test_codex_shell_first.py tests/test_cli_*.py -v
```
**结果**: 128 passed, 2 skipped in 8.39s.

### 3.2 完整测试套件回归
```bash
uv run pytest
```
**结果**: 1080 passed, 11 skipped in 57.31s.

### 3.3 代码规范检查 (Ruff)
```bash
uv run ruff check .
```
**结果**: All checks passed!
