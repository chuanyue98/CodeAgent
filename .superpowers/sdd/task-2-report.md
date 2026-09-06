# Task 2 执行与自检报告：规范化 Agent Gateway 默认关闭与状态声明 (AUDIT-001)

## 1. 状态：DONE

- **Git Commit**: `eb26685` (`fix(gateway): Agent Gateway 明确标记为实验性并默认关闭 (AUDIT-001)`)
- **文件变更**:
  - [core/web/server.py](file:///home/cy/github/chuanyue98/CodeAgent/core/web/server.py)
  - [tests/test_web_api.py](file:///home/cy/github/chuanyue98/CodeAgent/tests/test_web_api.py)
- **测试结果**: 45 passed (100%)
- **Lint 结果**: All checks passed

---

## 2. 任务背景与目标 (AUDIT-001)

Agent Gateway（基于 REST/WS 的按提供方适配的编程式接口）属于实验性子系统：
- 随着流式终端（streaming terminal）成为统一的对话交互界面，原始 Web UI 已被精简；
- 启动链路（`engines/start_*.py` / `core/engine_registry.py`）是产品的主适配层；
- 之前 `get_agent_gateway_settings()` 中 `enabled` 默认被设置为 `True`，导致未声明或未配置情况下默认启动了实验性网关；
- 本任务根据 AUDIT-001 要求，将 Agent Gateway 明确标记为实验性，默认策略调整为关闭（`False`），仅在显式传入环境变量 `CA_AGENT_GATEWAY_ENABLED=1` 或配置项 `"agent_gateway": {"enabled": True}` 时启用。

---

## 3. 具体改动

### 3.1 `core/web/server.py`
在 `get_agent_gateway_settings(config: dict)` 函数中：
- 将默认开启逻辑收敛为默认关闭：
  ```python
  "enabled": _env_bool(
      "CA_AGENT_GATEWAY_ENABLED", bool(raw.get("enabled", False))
  ),
  ```
- 增加了关于实验性子系统以及 AUDIT-001 设计决策的代码注释说明。

### 3.2 `tests/test_web_api.py`
添加与完善单元测试 `test_agent_gateway_defaults_to_off`：
- 在未配置环境变量且无特定配置时，断言 `get_agent_gateway_settings({})["enabled"] is False`；
- 在显式配置 `{"agent_gateway": {"enabled": True}}` 时，断言其为 `True`；
- 在环境变量 `CA_AGENT_GATEWAY_ENABLED="1"` 显式注入时，断言其为 `True`。

---

## 4. 验证记录

### 4.1 测试套件执行
```bash
uv run pytest tests/test_web_api.py tests/test_agent_gateway.py -v
```
**输出结果**：
```text
============================= test session starts ==============================
platform linux -- Python 3.13.13, pytest-9.1.1, pluggy-1.6.0 -- /home/cy/github/chuanyue98/CodeAgent/.venv/bin/python3
cachedir: .pytest_cache
rootdir: /home/cy/github/chuanyue98/CodeAgent
configfile: pyproject.toml
plugins: anyio-4.13.0, timeout-2.4.0, asyncio-1.3.0, cov-7.1.0
timeout: 60.0s
timeout method: signal
timeout func_only: False
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 45 items

tests/test_web_api.py::test_health_check PASSED                          [  2%]
tests/test_web_api.py::test_agent_gateway_settings_support_config_and_environment PASSED [  4%]
tests/test_web_api.py::test_agent_gateway_defaults_to_off PASSED         [  6%]
...
tests/test_agent_gateway.py::test_execute_command_failure_is_not_cached_and_unblocks_waiters PASSED [100%]

============================== 45 passed in 2.25s ==============================
```

### 4.2 Ruff 代码规范检查
```bash
uv run ruff check core/web/server.py tests/test_web_api.py
```
**输出结果**：
```text
All checks passed!
```

---

## 5. 交付物与结论

- 提交已生成：`eb26685 fix(gateway): Agent Gateway 明确标记为实验性并默认关闭 (AUDIT-001)`
- 针对 AUDIT-001 的安全与默认最小权限原则已落地，回归测试全部通过。
