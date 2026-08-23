from __future__ import annotations

from core.project_groups import resolve_project_group


def _rule(path, group):
    return {"path": str(path), "group": group}


def test_a_parent_rule_covers_every_repository_under_it(tmp_path):
    # The whole reason groups exist: register the parent once instead of
    # repeating the same group on every repository inside it.
    parent = tmp_path / "demo"
    repo = parent / "some-repo"
    repo.mkdir(parents=True)

    assert resolve_project_group(repo, [_rule(parent, "web")]) == "web"


def test_the_longest_matching_rule_wins(tmp_path):
    parent = tmp_path / "demo"
    repo = parent / "CodeAgent"
    repo.mkdir(parents=True)
    registry = [_rule(parent, "web"), _rule(repo, "codeagent")]

    assert resolve_project_group(repo, registry) == "codeagent"
    # Order must not matter — specificity does.
    assert resolve_project_group(repo, list(reversed(registry))) == "codeagent"
    # A sibling still falls back to the parent rule.
    sibling = parent / "other"
    sibling.mkdir()
    assert resolve_project_group(sibling, registry) == "web"


def test_an_exact_rule_still_matches(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    assert resolve_project_group(repo, [_rule(repo, "work")]) == "work"


def test_a_sibling_prefix_is_not_a_parent(tmp_path):
    # "…/demo-old" must not match a rule for "…/demo": string prefixes would
    # say yes, path parents say no.
    rule_dir = tmp_path / "demo"
    other = tmp_path / "demo-old"
    rule_dir.mkdir()
    other.mkdir()

    assert resolve_project_group(other, [_rule(rule_dir, "web")]) is None


def test_no_rule_returns_none(tmp_path):
    assert resolve_project_group(tmp_path, []) is None
    assert resolve_project_group(tmp_path, None) is None


def test_malformed_entries_are_skipped_not_fatal(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    registry = [
        "not-a-dict",
        {"path": None, "group": "x"},
        {"path": str(repo)},  # no group
        {"group": "y"},  # no path
        _rule(repo, "work"),
    ]

    assert resolve_project_group(repo, registry) == "work"
