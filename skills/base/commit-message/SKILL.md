---
name: commit-message
description: 生成符合规范的 Git 提交信息和分支名称，并执行隐私与格式审计。
---

# Commit Message (提交信息专家)

分析当前 Git 变更，生成结构化的中文提交消息和英文分支名称。

## Guidelines
1. **信息收集**：运行 `git status`、`git diff --stat HEAD` 和 `git diff HEAD --diff-filter=d` 获取完整的变更摘要和详细 diff。
2. **生成规范**：
    - **提交信息**：使用中文，格式为 `<type>(<scope>): <subject>`，包含 Body 和 Footer。
    - **分支名称**：使用英文，采用 kebab-case 格式。
3. **隐私审计**：将草案写入 `commit_draft.tmp`，运行 `python scripts/check_commit.py` 审计。严禁输出包含本地绝对路径（如 `D:\work\...`）的内容。
4. **输出约束**：提交信息和分支名称必须分别包裹在 ```text``` 代码块中，禁止使用自动链接或语义解析代码块。

## Examples
- **输入**: 修改了用户头像上传逻辑，增加了压缩功能。
- **输出**:
```text
feat(user): 优化头像上传流程

- 增加图像压缩处理
- 修复大文件上传超时问题

Close #123
```
