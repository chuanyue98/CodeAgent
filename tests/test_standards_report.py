"""规范注入状态行：判定优先级与输出通道的契约。

这行状态是用户判断"我的规范这次到底生效了没有"的唯一依据，所以两件事必须
钉死：什么情况算成功，以及它绝不能污染 stdout。
"""

from __future__ import annotations

from core.engine_base.standards_report import (
    StandardsDelivery,
    report_standards_delivery,
)


def test_synced_wins_over_every_other_reason(home, capsys):
    """已经 sync 过时，规范其实生效了，不该再被报成"未注入"。"""
    delivery = report_standards_delivery(
        "antigravity",
        "Antigravity",
        synced=True,
        skip_reason="a .cmd wrapper on Windows",
        failure="boom",
    )

    assert delivery is StandardsDelivery.VIA_USER_CONFIG
    err = capsys.readouterr().err
    assert "come from your user-level" in err
    assert "no system-prompt channel" not in err


def test_missing_channel_is_reported_with_a_sync_hint(home, capsys):
    """Antigravity 没有通道，此前是静默丢规范。"""
    delivery = report_standards_delivery("antigravity", "Antigravity")

    assert delivery is StandardsDelivery.UNSUPPORTED
    err = capsys.readouterr().err
    assert "no system-prompt channel" in err
    assert "ca sync --engine antigravity" in err
    assert str(home / ".gemini" / "config" / "GEMINI.md") in err


def test_skip_reason_beats_injection(home, capsys):
    delivery = report_standards_delivery(
        "codex", "Codex", skip_reason="a .cmd wrapper on Windows"
    )

    assert delivery is StandardsDelivery.SKIPPED
    assert "standards NOT injected" in capsys.readouterr().err


def test_failed_injection_is_not_silent(home, capsys):
    delivery = report_standards_delivery(
        "opencode",
        "OpenCode",
        failure="OPENCODE_CONFIG_CONTENT is not mergeable JSON",
    )

    assert delivery is StandardsDelivery.FAILED
    assert "standards injection failed" in capsys.readouterr().err


def test_injected_names_the_channel_from_the_registry(home, capsys):
    delivery = report_standards_delivery("claude", "Claude")

    assert delivery is StandardsDelivery.INJECTED
    assert "standards injected via system-prompt file" in capsys.readouterr().err


def test_everything_goes_to_stderr_so_headless_json_stays_parseable(home, capsys):
    """``ca codex -ni`` 与 ``ca opencode run`` 的 stdout 是机器可读的 JSON。"""
    for engine_key, name in (
        ("claude", "Claude"),
        ("antigravity", "Antigravity"),
        ("codex", "Codex"),
    ):
        report_standards_delivery(engine_key, name)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "standards" in captured.err
