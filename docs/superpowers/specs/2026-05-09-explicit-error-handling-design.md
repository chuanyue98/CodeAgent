# 设计文档：核心扫描器与配置加载器的异常显式化 (方案 C)

- **日期**: 2026-05-09
- **状态**: 草案
- **主题**: 重构 CodeAgent 的资源扫描与配置加载机制，将隐式的异常忽略转变为显式的元组返回。

## 1. 背景与目标

目前 CodeAgent 的多个核心组件（`HookScanner`, `PluginScanner`, `ConfigService` 等）在遇到错误（如文件损坏、JSON 格式错误）时，往往采用 `except Exception: pass` 或返回空字典 `{}`。这虽然提高了系统的鲁棒性，但导致配置错误难以被用户发现，增加了调试成本。

**目标**:
- 将 `scan()` 和 `get_config()` 的返回类型统一为 `tuple[数据, 警告列表]`。
- 引入调试模式，支持在控制台打印原始异常堆栈。
- 在 `ca doctor` 中集中暴露这些扫描过程中的警告。

## 2. 详细设计

### 2.1 接口变更 (Breaking Changes)

所有涉及资源扫描的方法签名将进行如下调整：

| 组件 | 方法 | 修改前 | 修改后 (Python 3.13+) |
| :--- | :--- | :--- | :--- |
| `ConfigService` | `get_config` | `dict` | `tuple[dict, list[str]]` |
| `HookScanner` | `scan` | `dict[str, dict]` | `tuple[dict[str, dict], list[str]]` |
| `PluginScanner` | `scan` | `dict[str, dict]` | `tuple[dict[str, dict], list[str]]` |
| `PromptScanner` | `scan` | `dict[str, list[str]]` | `tuple[dict[str, list[str]], list[str]]` |
| `SkillScanner` | `scan` | `dict[str, list[str]]` | `tuple[dict[str, list[str]], list[str]]` |

### 2.2 异常捕获逻辑

引入统一的警告收集模式：

```python
def scan(self) -> tuple[dict, list[str]]:
    data = {}
    warnings = []

    # ... 遍历逻辑 ...
    try:
        # 加载逻辑
        pass
    except Exception as e:
        msg = f"无法加载 [路径]: {e}"
        warnings.append(msg)
        if os.getenv("CA_DEBUG"):
            import traceback
            traceback.print_exc()

    return data, warnings
```

### 2.3 调用方适配

#### BaseEngine (`core/engine_base.py`)
- 在初始化时接收 `ConfigService.get_config()` 的元组，并处理警告。
- 在资源加载（Skills, Hooks, Plugins）时解包元组。

#### Web 路由 (`core/web/routers/*.py`)
- 修改 FastAPI 路由处理函数。
- 更新返回给前端的数据结构（可选，建议在 API 中保留 warnings 字段供前端展示）。

#### 诊断工具 (`core/doctor.py`)
- 修改 `check_config` 等检查函数，捕获并展示来自 Scanner 的 `warnings`。

## 3. 验收标准

1. **功能性**:
   - 当 `config.json` 损坏时，`ca doctor` 必须显示具体的 JSON 解析错误。
   - 当某个 Hook 的 `metadata.json` 损坏时，系统应跳过该 Hook 但在启动或诊断时显示警告。
2. **健壮性**:
   - 开启 `CA_DEBUG=1` 环境变量时，应能在控制台看到完整的异常堆栈。
3. **测试**:
   - 所有 Scanner 的单元测试通过，且断言已更新为元组格式。

## 4. 实施阶段计划

1. **阶段 1**: 重构 `ConfigService` 及其相关测试。
2. **阶段 2**: 逐个重构四大 Scanner (`Hook`, `Plugin`, `Prompt`, `Skill`)。
3. **阶段 3**: 更新 `BaseEngine` 适配逻辑。
4. **阶段 4**: 更新 Web API 与 `ca doctor`。
5. **阶段 5**: 全量运行测试并清理临时文件。
