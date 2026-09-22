"""Codex 两代 rollout 格式都要能读出用户发言。

2026-08 之后的 Codex 不再写 ``event_msg``/``user_message``，只剩
``response_item``。解析器当时把 ``response_item`` 里的 user 行当重复跳过，
于是新格式的会话解析出来全是 assistant：``ca history`` 看着还在，一
``ca switch`` 过去就成了一段没有人说话的记录，目标引擎里跟新会话没区别。
"""

from __future__ import annotations

import json

from core.session_history.parsers.codex_parser import parse_codex_session


def _write(tmp_path, rows: list[dict]):
    session_dir = tmp_path / ".codex" / "sessions" / "2026" / "09" / "22"
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / "rollout-2026-09-22T10-00-00-sess1.jsonl"
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def _meta():
    return {
        "timestamp": "2026-09-22T10:00:00.000Z",
        "type": "session_meta",
        "payload": {"id": "sess1", "cwd": "/repo"},
    }


def _response_user(text: str, when: str = "2026-09-22T10:00:01.000Z"):
    return {
        "timestamp": when,
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    }


def _response_assistant(text: str, when: str = "2026-09-22T10:00:02.000Z"):
    return {
        "timestamp": when,
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        },
    }


def _event_user(text: str, when: str = "2026-09-22T10:00:01.500Z"):
    return {
        "timestamp": when,
        "type": "event_msg",
        "payload": {"type": "user_message", "message": text},
    }


def test_the_new_format_keeps_the_users_turns(tmp_path):
    path = _write(
        tmp_path,
        [
            _meta(),
            _response_user("GUI 有哪些体验能改？"),
            _response_assistant("我先看入口。"),
            _response_user("再看看权限提示。", "2026-09-22T10:00:03.000Z"),
            _response_assistant("这条链路我核一遍。", "2026-09-22T10:00:04.000Z"),
        ],
    )

    session = parse_codex_session(path)

    assert [m.role for m in session.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert session.messages[0].content == "GUI 有哪些体验能改？"


def test_the_old_format_does_not_double_count_a_turn(tmp_path):
    # 老格式同一句话既有 response_item 又有 event_msg。
    path = _write(
        tmp_path,
        [
            _meta(),
            _response_user("跑一下测试"),
            _event_user("跑一下测试"),
            _response_assistant("好。"),
        ],
    )

    session = parse_codex_session(path)

    assert [m.role for m in session.messages] == ["user", "assistant"]
    assert session.messages[0].content == "跑一下测试"


def test_codex_own_injections_are_not_mistaken_for_the_user(tmp_path):
    # Codex 把环境快照、项目约定、子代理回执都塞进 user 角色发给模型。
    path = _write(
        tmp_path,
        [
            _meta(),
            _response_user(
                "<environment_context>\n  <cwd>/repo</cwd>\n</environment_context>"
            ),
            _response_user("# AGENTS.md instructions for /repo\n\n<INSTRUCTIONS>x"),
            _response_user("<subagent_notification>\n{}\n</subagent_notification>"),
            _response_user("真正的问题在哪？"),
            _response_assistant("在这。"),
        ],
    )

    session = parse_codex_session(path)

    assert [m.content for m in session.messages if m.role == "user"] == [
        "真正的问题在哪？"
    ]


def test_a_session_of_only_injections_stays_invisible(tmp_path):
    path = _write(
        tmp_path,
        [_meta(), _response_user("<environment_context>\n</environment_context>")],
    )

    assert parse_codex_session(path) is None
