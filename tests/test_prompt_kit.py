"""prompt_kit.py 的单元测试"""

import pytest

from core.prompt_kit import (
    get_prompts_from_directory,
    prompt_general,
    prompt_review,
    prompt_standards,
)


@pytest.fixture
def temp_prompt_root(tmp_path):
    """创建临时提示词目录结构"""
    prompt_dir = tmp_path / "prompt"
    prompt_dir.mkdir()

    # 创建 base 分组
    base_dir = prompt_dir / "base"
    base_dir.mkdir()
    (base_dir / "general.basic.md").write_text(
        "### Base Standards ###\nSome base content.", encoding="utf-8"
    )

    # 创建 coding 分组
    coding_dir = prompt_dir / "coding"
    coding_dir.mkdir()
    (coding_dir / "class.md").write_text(
        "## 类\nPython class standards.", encoding="utf-8"
    )

    # 创建 review 分组
    review_dir = prompt_dir / "review"
    review_dir.mkdir()
    (review_dir / "pr_review.md").write_text(
        "### Review Standards ###\nReview rules.", encoding="utf-8"
    )

    return prompt_dir


def test_prompt_general(temp_prompt_root):
    """测试获取通用提示词"""
    prompt = prompt_general(prompt_root=temp_prompt_root)
    assert isinstance(prompt, str)
    # 验证是否包含 Base Standards
    assert "### Base Standards ###" in prompt
    # 验证是否包含 Python 规范的内容 (例如 "类")
    assert "类" in prompt


def test_prompt_review(temp_prompt_root):
    """测试获取审查提示词"""
    prompt = prompt_review(prompt_root=temp_prompt_root)
    assert isinstance(prompt, str)
    assert "### Review Standards ###" in prompt


def test_get_prompts_from_directory(temp_prompt_root):
    """测试从目录获取提示词"""
    standards_dir = temp_prompt_root / "coding"

    prompt = get_prompts_from_directory(standards_dir)
    assert isinstance(prompt, str)
    # 验证是否包含目录下的内容，例如 "类"
    assert "类" in prompt


def test_parse_args():
    """测试命令行参数解析"""
    from core.prompt_kit import parse_args

    choices = ["general", "review"]

    # 测试指定 prompt
    parsed_args, parser = parse_args(choices, ["-p", "general"])
    assert parsed_args.prompt == "general"

    # 测试指定分组
    parsed_args, parser = parse_args(choices, ["-g", "base", "web"])
    assert parsed_args.groups == ["base", "web"]


@pytest.fixture
def heading_prompt_root(tmp_path):
    """正文带标题层级和围栏代码块的分组，用来验证拼接。"""
    base_dir = tmp_path / "prompt" / "base"
    base_dir.mkdir(parents=True)
    (base_dir / "general.basic.md").write_text(
        "# 开发指南\n"
        "\n"
        "## 任务状态\n"
        "\n"
        "阶段格式：\n"
        "\n"
        "```markdown\n"
        "## 阶段 N: [名称]\n"
        "**状态**: [未开始]\n"
        "```\n",
        encoding="utf-8",
    )
    return tmp_path / "prompt"


def test_standards_group_heading_is_on_its_own_line(heading_prompt_root):
    """分组标题后必须换行，否则它的 ``###`` 会和正文首行的 ``#`` 连成一行。"""
    prompt = prompt_standards(groups=["base"], prompt_root=heading_prompt_root)

    assert "### Base Standards ###\n" in prompt
    assert "Standards ####" not in prompt


def test_standards_body_headings_are_demoted(heading_prompt_root):
    """正文标题整体降到分组标题（h3）之下，避免 h1 挂在 h3 里面。"""
    prompt = prompt_standards(groups=["base"], prompt_root=heading_prompt_root)

    assert "#### 开发指南" in prompt
    assert "##### 任务状态" in prompt
    assert "\n# 开发指南" not in prompt


def test_standards_leaves_fenced_code_untouched(heading_prompt_root):
    """围栏代码块里的 ``#`` 是正文示例，不能当成标题降级。"""
    prompt = prompt_standards(groups=["base"], prompt_root=heading_prompt_root)

    assert "## 阶段 N: [名称]" in prompt
    assert "##### 阶段 N" not in prompt
