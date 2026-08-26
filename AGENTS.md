# AGENTS.md — 本项目对所有 AI Agent 的工作约定

无论你是什么工具（CodeBuddy / Claude Code / Codex / Gemini CLI / OpenCode / WorkBuddy 等），在本仓库干活前必须先读完本文件并严格遵守。

## 依赖与运行环境（最高优先级，最容易违反）

- 本项目使用 **uv** 做依赖管理。**禁止** `pip install`、`python -m venv`、`virtualenv`、`conda`。
- 运行任何 Python 命令一律通过 `uv run`：
  - 跑测试：`uv run pytest`
  - 执行脚本：`uv run python xxx.py`
  - 模块方式：`uv run python -m core.xxx`
  - Lint：`uv run ruff check .`
  - 类型检查：`uv run mypy core`
- 添加依赖：`uv add <pkg>`；添加开发依赖：`uv add --group dev <pkg>`。
- 仓库根目录的 `.venv` 由 uv 自动管理，**不要**手动重建、激活或往里装包；直接 `uv run` 即可。
- `uv.lock` 与 `pyproject.toml` 必须保持同步，两者都提交。

## 项目速览

- Python 项目，核心代码在 `core/`，测试在 `tests/`（pytest，配置见 `pyproject.toml`）。
- 改动完成后，交付前必须通过：`uv run pytest` 和 `uv run ruff check .`。
- 提交信息、注释与文档使用中文。

## 常见错误（Agent 历史前科，勿再犯）

- ❌ `python -m venv .venv` / `pip install -r requirements.txt` → ✅ `uv sync`
- ❌ `python -m pytest` → ✅ `uv run pytest`
- ❌ 手动 `source .venv/bin/activate` → ✅ 不需要，`uv run` 自带环境
