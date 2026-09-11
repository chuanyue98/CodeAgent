"""分析磁盘缓存的失效策略：按输入指纹，而不是按时间。

缓存过期曾是一个 5 分钟计时器，于是任何一次闲置后的重启都会触发整轮采集
（~3.3s），哪怕输入一个字都没变。这里锁定替代它的三条规则：输入没变就是
命中，历史归档变了就失效，schema/费率变了也失效。
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from core.analytics import disk_cache


@pytest.fixture
def redirected(tmp_path):
    """把归档与缓存都指到 tmp，避免碰开发者真实的那两份。"""
    history_file = tmp_path / ".ca_analytics_history.jsonl"
    cache_file = tmp_path / ".ca_analytics_cache.json"
    with (
        patch("core.analytics.history._history_path", return_value=history_file),
        patch(
            "core.analytics.disk_cache._default_cache_path", return_value=cache_file
        ),
    ):
        history_file.write_text("", encoding="utf-8")
        yield history_file, cache_file


def test_hit_when_inputs_unchanged(redirected):
    disk_cache.save_cache({"v": 1})
    assert disk_cache.load_cache() == {"v": 1}


def test_miss_when_history_grows(redirected):
    history_file, _ = redirected
    disk_cache.save_cache({"v": 1})
    assert disk_cache.load_cache() == {"v": 1}

    # 采集器追加了一条 → 归档的 (mtime, size) 变了 → 旧聚合不能再信。
    with open(history_file, "a", encoding="utf-8") as f:
        f.write('{"target": "claude"}\n')
    assert disk_cache.load_cache() is None


def test_missing_history_is_a_valid_input(redirected):
    """归档还没有时，"不存在"本身也是可缓存的状态。"""
    history_file, _ = redirected
    history_file.unlink()
    disk_cache.save_cache({"v": 1})
    assert disk_cache.load_cache() == {"v": 1}


def test_schema_bump_drops_cache(redirected):
    _, cache_file = redirected
    disk_cache.save_cache({"v": 1})
    doc = json.loads(cache_file.read_text(encoding="utf-8"))
    doc["version"] = disk_cache.CACHE_SCHEMA_VERSION - 1
    cache_file.write_text(json.dumps(doc), encoding="utf-8")
    assert disk_cache.load_cache() is None


def test_pricing_change_drops_cache(redirected):
    disk_cache.save_cache({"v": 1})
    with patch(
        "core.analytics.disk_cache.pricing_fingerprint", return_value="different"
    ):
        assert disk_cache.load_cache() is None


def test_expired_cache_is_rejected_but_still_servable(redirected, monkeypatch):
    """只因"太旧"被拒的缓存，仍然可以当陈旧值用（后台刷新期间先顶上）。

    归档只会被采集本身写入，所以光靠输入指纹永远等不到下一次采集；这个上限
    是让新用量进得来的唯一途径。
    """
    disk_cache.save_cache({"v": 1})
    monkeypatch.setattr(disk_cache, "CACHE_MAX_AGE_SECONDS", -1)
    assert disk_cache.load_cache() is None
    assert disk_cache.load_cache(allow_stale=True) == {"v": 1}


def test_input_change_is_not_servable_even_as_stale(redirected, monkeypatch):
    """输入变了就不能拿旧值糊弄——过期和"来源变了"是两回事。"""
    disk_cache.save_cache({"v": 1})
    monkeypatch.setattr(disk_cache, "_source_key", lambda: "different")
    assert disk_cache.load_cache() is None
    assert disk_cache.load_cache(allow_stale=True) is None
