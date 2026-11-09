"""状态文件读不懂时改用上一份完好的副本（core/utils/last_good.py）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.injection_ledger import InjectionLedger, ledger_path_for
from core.services.config_service import ConfigService
from core.utils.last_good import (
    BAD_COPY_INFIX,
    keep_last_good,
    last_good_path,
    looks_crash_damaged,
    read_with_fallback,
)


def _zero_out(path: Path) -> None:
    """断电后留下的样子：长度不变，每个字节都是 0。"""
    path.write_bytes(b"\x00" * len(path.read_bytes()))


def _bad_copies(path: Path) -> list[Path]:
    return sorted(path.parent.glob(f"{path.name}{BAD_COPY_INFIX}*"))


# ── 模块本身 ────────────────────────────────────────────────────────────


def test_crash_signature_is_empty_or_zero_bytes():
    assert looks_crash_damaged(b"")
    assert looks_crash_damaged(b"\x00" * 64)
    assert not looks_crash_damaged(b"{ oops")


def test_missing_file_is_not_damage(tmp_path):
    assert read_with_fallback(tmp_path / "x.json", json.loads) == (None, None, True)


def test_damaged_file_reads_its_last_good_copy(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    keep_last_good(path, json.loads)
    _zero_out(path)

    data, note, intact = read_with_fallback(path, json.loads)
    assert data == {"a": 1}
    assert not intact
    assert str(last_good_path(path)) in note


def test_damaged_file_is_set_aside_not_kept_as_good(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    keep_last_good(path, json.loads)
    _zero_out(path)

    keep_last_good(path, json.loads)
    keep_last_good(path, json.loads)  # 再来一次，完好副本仍不被坏文件覆盖
    assert json.loads(last_good_path(path).read_text(encoding="utf-8")) == {"a": 1}
    copies = _bad_copies(path)
    assert copies and copies[0].read_bytes() == path.read_bytes()


def test_no_good_copy_reports_the_reason(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{", encoding="utf-8")
    data, note, intact = read_with_fallback(path, json.loads)
    assert data is None and not intact
    assert "读不懂" in note


# ── 注入账本 ────────────────────────────────────────────────────────────


def _ledger_with(settings: Path, entries: list[dict]) -> InjectionLedger:
    ledger = InjectionLedger(settings)
    ledger.original = None
    ledger.entries = entries
    ledger.save()
    return ledger


def test_zeroed_ledger_is_read_from_its_last_good_copy(tmp_path):
    settings = tmp_path / "settings.json"
    _ledger_with(settings, [{"key": "first"}])
    _ledger_with(settings, [{"key": "first"}, {"key": "second"}])
    _zero_out(ledger_path_for(settings))

    ledger = InjectionLedger(settings)
    assert ledger.load()
    # 副本是上一代：少了最近一次写的条目，但不是空的。
    assert ledger.entries == [{"key": "first"}]


def test_deleting_the_ledger_removes_its_copy(tmp_path):
    settings = tmp_path / "settings.json"
    _ledger_with(settings, [])
    _ledger_with(settings, [])
    ledger = InjectionLedger(settings)
    ledger.delete()
    assert not ledger_path_for(settings).exists()
    assert not last_good_path(ledger_path_for(settings)).exists()
    assert not InjectionLedger(settings).load()


# ── ca 的 config.json ──────────────────────────────────────────────────


@pytest.fixture
def service(tmp_path):
    svc = ConfigService(tmp_path / "config.json")
    svc.update_config({"project_registry": [{"path": "/p", "group": "g"}]})
    svc.add_project("/q", "g")  # 第二次写：上一份完好的副本就位
    return svc


def test_zeroed_config_still_reads_projects(service):
    _zero_out(service.config_path)
    data, warnings = service.get_config()
    assert data["project_registry"] == [{"path": "/p", "group": "g"}]
    assert "Failed to parse config.json" in warnings[0]


def test_zeroed_config_is_recovered_on_next_write(service):
    _zero_out(service.config_path)
    service.add_project("/r", "g")

    data, warnings = service.get_config()
    assert not warnings
    # 副本是上一代（只有 /p），/q 那次写入随损坏一起丢了。
    assert [p["path"] for p in data["project_registry"]] == ["/p", "/r"]
    assert _bad_copies(service.config_path)


def test_hand_edit_typo_is_never_overwritten(service):
    """手改出错的文件里有用户的改动：只读副本，写入照样拒绝。"""
    service.config_path.write_text('{"project_registry": [oops]}', encoding="utf-8")
    data, warnings = service.get_config()
    assert data["project_registry"]  # 读仍可用
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        service.add_project("/r", "g")
    assert "oops" in service.config_path.read_text(encoding="utf-8")
