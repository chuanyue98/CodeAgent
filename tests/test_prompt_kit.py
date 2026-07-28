"""prompt_kit.py 的单元测试"""

import pytest

from core.prompt_kit import get_prompts_from_directory, prompt_general, prompt_review


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
