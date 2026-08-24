"""A deleted template group must stay deleted.

Seeding used to key on "is this group present", so removing one of the
template groups in Settings bought nothing: the next server start rebuilt it,
and there was no way to express "not this one". Seeding now happens once, on a
config that has never had a ``groups`` key.
"""

from __future__ import annotations

import json

import pytest

from core.web import server


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(server, "CONFIG_PATH", path)
    return path


def _run(config_path, initial: dict | None) -> dict:
    if initial is not None:
        config_path.write_text(json.dumps(initial), encoding="utf-8")
    server.initialize_default_groups()
    return json.loads(config_path.read_text(encoding="utf-8"))


def test_a_config_with_no_groups_key_gets_the_templates(config_path):
    result = _run(config_path, {})

    assert set(result["groups"]) == set(server.DEFAULT_GROUP_CATEGORIES)


def test_a_deleted_template_group_is_not_rebuilt(config_path):
    seeded = _run(config_path, {})
    victim = next(iter(server.DEFAULT_GROUP_CATEGORIES))
    del seeded["groups"][victim]
    config_path.write_text(json.dumps(seeded), encoding="utf-8")

    result = _run(config_path, None)

    assert victim not in result["groups"]


def test_deleting_every_template_group_still_leaves_it_deleted(config_path):
    # An empty groups map is a decision, not a missing key.
    seeded = _run(config_path, {})
    seeded["groups"] = {}
    config_path.write_text(json.dumps(seeded), encoding="utf-8")

    result = _run(config_path, None)

    assert result["groups"] == {}


def test_an_existing_group_still_gets_missing_sub_keys_backfilled(config_path):
    seeded = _run(config_path, {})
    survivor = next(iter(server.DEFAULT_GROUP_CATEGORIES))
    del seeded["groups"][survivor]["prompts"]
    del seeded["groups"][survivor]["plugins"]
    config_path.write_text(json.dumps(seeded), encoding="utf-8")

    result = _run(config_path, None)

    # Back-filling a group that exists is fine; resurrecting one that does
    # not is what was wrong.
    assert "prompts" in result["groups"][survivor]
    assert "plugins" in result["groups"][survivor]


def test_a_user_group_is_left_alone(config_path):
    result = _run(config_path, {"groups": {"mine": {"skills": ["a/b"]}}})

    assert result["groups"]["mine"] == {"skills": ["a/b"]}
    # And no templates are injected into a config that already made its own
    # choices about groups.
    assert set(result["groups"]) == {"mine"}
