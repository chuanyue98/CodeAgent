from __future__ import annotations

import pytest

from core.engine_base import launch_args
from core.engine_base.launch_args import is_batch_shim, split_passthrough


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ([], ("", [])),
        (["修一下", "登录"], ("修一下 登录", [])),
        (["-r"], ("", ["-r"])),
        (["-s", "ses_1"], ("", ["-s", "ses_1"])),
        # opus 是 --model 的值还是提示词分不清，所以整段交给引擎。
        (["--model", "opus", "fix", "bug"], ("", ["--model", "opus", "fix", "bug"])),
    ],
)
def test_split_passthrough(args, expected):
    assert split_passthrough(args) == expected


def test_multiline_prompt_starting_with_a_dash_is_still_a_message():
    prompt = "- 第一项\n- 第二项"

    assert split_passthrough([prompt]) == (prompt, [])


def test_lone_dash_is_a_word_not_a_flag():
    assert split_passthrough(["-"]) == ("-", [])


def test_subcommand_passes_through_only_when_declared():
    assert split_passthrough(["resume", "abc"], {"resume"}) == ("", ["resume", "abc"])
    assert split_passthrough(["resume", "abc"]) == ("resume abc", [])


def test_batch_shim_is_never_reported_off_windows(monkeypatch):
    monkeypatch.setattr(launch_args, "_IS_WINDOWS", False)
    monkeypatch.setattr(
        launch_args.shutil, "which", lambda *_a, **_k: r"D:\npm\codex.cmd"
    )

    assert is_batch_shim("codex", {}) is False


@pytest.mark.parametrize(
    ("resolved", "expected"),
    [
        (r"D:\npm\codex.CMD", True),
        (r"D:\npm\codebuddy.bat", True),
        (r"C:\Users\me\.local\bin\claude.exe", False),
        (None, False),
    ],
)
def test_batch_shim_detection_on_windows(monkeypatch, resolved, expected):
    monkeypatch.setattr(launch_args, "_IS_WINDOWS", True)
    monkeypatch.setattr(launch_args.shutil, "which", lambda *_a, **_k: resolved)

    assert is_batch_shim("codex", {"PATH": "unused"}) is expected
