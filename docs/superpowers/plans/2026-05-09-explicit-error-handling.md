# 核心扫描器与配置加载器的异常显式化 (方案 C) 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 CodeAgent 的核心资源扫描器和配置服务，将返回类型统一为 `tuple[数据, 警告列表]`，从而显式化潜在的加载错误，并在调试模式下打印堆栈。

**Architecture:** 采用“显式元组返回”模式。修改所有扫描器的 `scan()` 方法和 `ConfigService.get_config()` 方法。引入 `CA_DEBUG` 环境变量控制详细错误输出。在 `ca doctor` 中集成警告展示逻辑。

**Tech Stack:** Python 3.13+, pytest

---

### Task 1: 重构 ConfigService

**Files:**
- Modify: `core/services/config_service.py`
- Modify: `tests/test_config_service.py`

- [ ] **Step 1: 修改 ConfigService.get_config 以返回元组**
```python
# core/services/config_service.py
def get_config(self) -> tuple[dict, list[str]]:
    warnings = []
    if not self.config_path.exists():
        return {}, []
    try:
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f), []
    except Exception as e:
        warnings.append(f"Failed to parse config.json: {e}")
        if os.getenv("CA_DEBUG"):
            import traceback
            traceback.print_exc()
        return {}, warnings
```

- [ ] **Step 2: 修改 ConfigService.add_project 和 delete_project 的调用点**
解包 `self.get_config()` 返回的元组。

- [ ] **Step 3: 更新测试用例 `tests/test_config_service.py`**
更新断言以匹配元组返回格式。

- [ ] **Step 4: 运行测试并提交**
Run: `pytest tests/test_config_service.py`

---

### Task 2: 重构 HookScanner

**Files:**
- Modify: `core/hook_scanner.py`
- Modify: `tests/test_hook_scanner.py`

- [ ] **Step 1: 修改 HookScanner.scan 返回类型**
在 `try...except` 块中收集警告，返回 `(result, warnings)`。

- [ ] **Step 2: 更新 `get_hooks_to_inject` 调用点**
```python
scanned, scan_warnings = scanner.scan()
# ...
```

- [ ] **Step 3: 更新测试用例 `tests/test_hook_scanner.py`**

- [ ] **Step 4: 运行测试并提交**
Run: `pytest tests/test_hook_scanner.py`

---

### Task 3: 重构 PluginScanner

**Files:**
- Modify: `core/plugin_scanner.py`
- Modify: `tests/test_plugin.py`

- [ ] **Step 1: 修改 PluginScanner.scan 返回类型**
收集 `metadata.json` 解析错误。

- [ ] **Step 2: 更新 `get_plugins_to_mount` 调用点**

- [ ] **Step 3: 更新测试用例 `tests/test_plugin.py`**

- [ ] **Step 4: 运行测试并提交**
Run: `pytest tests/test_plugin.py`

---

### Task 4: 重构 PromptScanner

**Files:**
- Modify: `core/prompt_scanner.py`
- Modify: `tests/test_prompt_scanner.py`

- [ ] **Step 1: 修改 PromptScanner.scan 返回类型**
虽然 `PromptScanner` 主要是 glob 文件，但仍需对齐签名。

- [ ] **Step 2: 更新 `get_prompts_to_inject` 调用点**

- [ ] **Step 3: 更新测试用例 `tests/test_prompt_scanner.py`**

- [ ] **Step 4: 运行测试并提交**
Run: `pytest tests/test_prompt_scanner.py`

---

### Task 5: 重构 SkillScanner

**Files:**
- Modify: `core/skill_scanner.py`
- Modify: `tests/test_resource_services.py`

- [ ] **Step 1: 修改 SkillScanner.scan 返回类型**
记录发现无效技能目录时的警告。

- [ ] **Step 2: 更新 `get_skills_to_mount` 调用点**

- [ ] **Step 3: 更新测试用例 `tests/test_resource_services.py`**

- [ ] **Step 4: 运行测试并提交**
Run: `pytest tests/test_resource_services.py`

---

### Task 6: 重构 BaseEngine 与 EnvironmentManager

**Files:**
- Modify: `core/engine_base.py`

- [ ] **Step 1: 适配 BaseEngine.__init__**
处理 `get_config()` 和 Scanners 初始化时的元组返回。

- [ ] **Step 2: 适配 BaseEngine 中的所有扫描调用**
包括 `get_skills_to_mount`, `get_plugins_to_mount`, `get_prompts_to_inject`, `get_hooks_to_inject`。

- [ ] **Step 3: 运行验证性测试**
Run: `pytest tests/test_engine_base.py`

---

### Task 7: 增强 ca doctor

**Files:**
- Modify: `core/doctor.py`

- [ ] **Step 1: 修改 check_config 以显示 Scanner 警告**
```python
def check_config(section: Section, root: Path) -> Optional[dict]:
    # ...
    cfg, warnings = config_service.get_config()
    for w in warnings:
        section.add(WARN, "config.json", w)
    # ...
```

- [ ] **Step 2: 更新所有 Resolution 检查以显示警告**
解包并展示来自各个 Scanner 的警告。

---

### Task 8: Web API 适配

**Files:**
- Modify: `core/web/routers/*.py` (config.py, hooks.py, plugins.py, prompts.py, skills.py)

- [ ] **Step 1: 更新所有路由中的 Service/Scanner 调用**
解包元组，暂时忽略 Web 端的 warnings（或根据需要添加至响应模型）。

- [ ] **Step 2: 运行 Web API 测试**
Run: `pytest tests/test_web_api.py`
