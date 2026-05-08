#!/usr/bin/env python3
"""
技能初始化器 - 从模板创建一个新技能

用法:
    init_skill.py <skill-name> --path <path>

示例:
    init_skill.py my-new-skill --path skills/public
    init_skill.py my-api-helper --path skills/private
    init_skill.py custom-skill --path /custom/location
"""

import sys
from pathlib import Path


SKILL_TEMPLATE = """
---
name: {skill_name}
description: [TODO: 完整且信息丰富地解释该技能的作用以及何时使用它。包括何时使用此技能——触发它的特定场景、文件类型或任务。]
---

# {skill_title}

## 概览

[TODO: 1-2 句话解释此技能启用了什么]

## 组织此技能

[TODO: 选择最适合此技能目的的结构。常见模式：

**1. 基于工作流** (最适合顺序过程)
- 当有清晰的逐步程序时效果很好
- 示例：DOCX 技能，包含“工作流决策树” → “阅读” → “创建” → “编辑”
- 结构：## 概览 → ## 工作流决策树 → ## 步骤 1 → ## 步骤 2...

**2. 基于任务** (最适合工具集合)
- 当技能提供不同的操作/能力时效果很好
- 示例：PDF 技能，包含“快速开始” → “合并 PDF” → “拆分 PDF” → “提取文本”
- 结构：## 概览 → ## 快速开始 → ## 任务类别 1 → ## 任务类别 2...

**3. 参考文档/指南** (最适合标准或规范)
- 对品牌指南、编码标准或需求效果很好
- 示例：品牌风格，包含“品牌指南” → “颜色” → “排版” → “特性”
- 结构：## 概览 → ## 指南 → ## 规范 → ## 用法...

**4. 基于能力** (最适合集成系统)
- 当技能提供多个相互关联的功能时效果很好
- 示例：产品管理，包含“核心能力” → 编号的能力列表
- 结构：## 概览 → ## 核心能力 → ### 1. 功能 → ### 2. 功能...

模式可以按需混合搭配。大多数技能结合了多种模式（例如，从基于任务开始，为复杂操作添加工作流）。

完成后删除这整个“组织此技能”部分——这只是指导。]

## [TODO: 根据选择的结构替换为第一个主要部分]

[TODO: 在此添加内容。参见现有技能中的示例：
- 技术技能的代码示例
- 复杂工作流的决策树
- 具有现实用户请求的具体示例
- 按需引用脚本/模板/参考文档]

## 资源

此技能包含示例资源目录，演示如何组织不同类型的配套资源：

### scripts/
可以直接运行以执行特定操作的可执行代码（Python/Bash 等）。

**来自其他技能的示例：**
- PDF 技能：`fill_fillable_fields.py`，`extract_form_field_info.py` - PDF 操作工具
- DOCX 技能：`document.py`，`utilities.py` - 用于文档处理的 Python 模块

**适用于：** Python 脚本、Shell 脚本或任何执行自动化、数据处理或特定操作的可执行代码。

**注意：** 脚本可以在不加载到上下文中的情况下执行，但仍可以被 Agent 读取以进行修补或环境调整。

### references/
旨在加载到上下文中以通知 Agent 的过程和思考的文档和参考材料。

**来自其他技能的示例：**
- 产品管理：`communication.md`，`context_building.md` - 详细的工作流指南
- BigQuery：API 参考文档和查询示例
- 财务：架构文档，公司政策

**适用于：** 深度文档、API 参考、数据库架构、综合指南或 Agent 工作时应参考的任何详细信息。

### assets/
不打算加载到上下文中，而是在 Agent 生成的输出中使用的文件。

**来自其他技能的示例：**
- 品牌风格：PowerPoint 模板文件 (.pptx)，Logo 文件
- 前端构建器：包含 HTML/React 脚手架项目目录的 hello-world/
- 排版：字体文件 (.ttf, .woff2)

**适用于：** 模板、脚手架代码、文档模板、图像、图标、字体或任何要在最终输出中复制或使用的文件。

---

**任何不需要的目录都可以删除。** 并非每个技能都需要所有三种类型的资源。
"""

EXAMPLE_SCRIPT_CONTENT = """#!/usr/bin/env python3
{skill_name} 的示例辅助脚本

这是一个可以直接执行的占位符脚本。
替换为实际实现，如果不需要则删除。

来自其他技能的真实脚本示例：
- pdf/scripts/fill_fillable_fields.py - 填充 PDF 表单字段
- pdf/scripts/convert_pdf_to_images.py - 将 PDF 页面转换为图像

def main():
    print("这是 {skill_name} 的示例脚本")
    # TODO: 在此添加实际脚本逻辑
    # 这可以是数据处理、文件转换、API 调用等。

if __name__ == "__main__":
    main()
"""

EXAMPLE_REFERENCE = """# {skill_title} 的参考文档

这是一个详细参考文档的占位符。
替换为实际参考内容，如果不需要则删除。

来自其他技能的真实参考文档示例：
- product-management/references/communication.md - 状态更新的综合指南
- product-management/references/context_building.md - 收集上下文的深入探讨
- bigquery/references/ - API 参考和查询示例

## 何时参考文档有用

参考文档非常适合：
- 综合 API 文档
- 详细工作流指南
- 复杂的多步骤过程
- 对于主 SKILL.md 来说太长的信息
- 仅特定用例需要的内容

## 结构建议

### API 参考示例
- 概览
- 身份验证
- 带示例的端点
- 错误代码
- 速率限制

### 工作流指南示例
- 先决条件
- 逐步说明
- 常见模式
- 故障排除
- 最佳实践
"""

EXAMPLE_ASSET = """# 示例静态资源文件

此占位符表示静态资源文件将被存储的位置。
替换为实际静态资源文件（模板、图像、字体等），如果不需要则删除。

静态资源文件不打算加载到上下文中，而是在
Agent 生成的输出中使用。

来自其他技能的示例静态资源文件：
- 品牌指南：logo.png，slides_template.pptx
- 前端构建器：带有 HTML/React 脚手架的 hello-world/ 目录
- 排版：custom-font.ttf，font-family.woff2
- 数据：sample_data.csv，test_dataset.json

## 常见静态资源类型

- 模板：.pptx，.docx，脚手架目录
- 图像：.png，.jpg，.svg，.gif
- 字体：.ttf，.otf，.woff，.woff2
- 脚手架代码：项目目录，入门文件
- 图标：.ico，.svg
- 数据文件：.csv，.json，.xml，.yaml

注意：这是一个文本占位符。实际静态资源可以是任何文件类型。
"""


def title_case_skill_name(skill_name):
    """Convert hyphenated skill name to Title Case for display."""
    return " ".join(word.capitalize() for word in skill_name.split("-"))


def init_skill(skill_name, path):
    """
    Initialize a new skill directory with template SKILL.md.

    Args:
        skill_name: Name of the skill
        path: Path where the skill directory should be created

    Returns:
        Path to created skill directory, or None if error
    """
    # Determine skill directory path
    skill_dir = Path(path).resolve() / skill_name

    # Check if directory already exists
    if skill_dir.exists():
        print(f"❌ 错误: 技能目录已存在: {skill_dir}")
        return None

    # Create skill directory
    try:
        skill_dir.mkdir(parents=True, exist_ok=False)
        print(f"✅ 已创建技能目录: {skill_dir}")
    except Exception as e:
        print(f"❌ 创建目录时出错: {e}")
        return None

    # Create SKILL.md from template
    skill_title = title_case_skill_name(skill_name)
    skill_content = SKILL_TEMPLATE.format(
        skill_name=skill_name, skill_title=skill_title
    )

    skill_md_path = skill_dir / "SKILL.md"
    try:
        skill_md_path.write_text(skill_content, encoding="utf-8")
        print("✅ 已创建 SKILL.md")
    except Exception as e:
        print(f"❌ 创建 SKILL.md 时出错: {e}")
        return None

    # Create resource directories with example files
    try:
        # Create scripts/ directory with example script
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        example_script = scripts_dir / "example.py"
        example_script.write_text(
            EXAMPLE_SCRIPT_CONTENT.format(skill_name=skill_name), encoding="utf-8"
        )
        example_script.chmod(0o755)
        print("✅ 已创建 scripts/example.py")

        # Create references/ directory with example reference doc
        references_dir = skill_dir / "references"
        references_dir.mkdir(exist_ok=True)
        example_reference = references_dir / "api_reference.md"
        example_reference.write_text(
            EXAMPLE_REFERENCE.format(skill_title=skill_title), encoding="utf-8"
        )
        print("✅ 已创建 references/api_reference.md")

        # Create assets/ directory with example asset placeholder
        assets_dir = skill_dir / "assets"
        assets_dir.mkdir(exist_ok=True)
        example_asset = assets_dir / "example_asset.txt"
        example_asset.write_text(EXAMPLE_ASSET, encoding="utf-8")
        print("✅ 已创建 assets/example_asset.txt")
    except Exception as e:
        print(f"❌ 创建资源目录时出错: {e}")
        return None

    # Print next steps
    print(f"\\n✅ 技能 '{skill_name}' 已成功初始化于 {skill_dir}")
    print("\\n下一步:")
    print("1. 编辑 SKILL.md 以完成 TODO 项目并更新描述")
    print("2. 自定义或删除 scripts/、references/ 和 assets/ 中的示例文件")
    print("3. 准备好检查技能结构时运行验证器")

    return skill_dir


def main():
    if len(sys.argv) < 4 or sys.argv[2] != "--path":
        print("用法: init_skill.py <skill-name> --path <path>")
        print("\\n技能名称要求:")
        print("  - 连字符命名法 (例如 'data-analyzer')")
        print("  - 仅小写字母、数字和连字符")
        print("  - 最多 40 个字符")
        print("  - 必须与目录名完全匹配")
        print("\\n示例:")
        print("  init_skill.py my-new-skill --path skills/public")
        print("  init_skill.py my-api-helper --path skills/private")
        print("  init_skill.py custom-skill --path /custom/location")
        sys.exit(1)

    skill_name = sys.argv[1]
    path = sys.argv[3]

    print(f"🚀 正在初始化技能: {skill_name}")
    print(f"   位置: {path}")
    print()

    result = init_skill(skill_name, path)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
