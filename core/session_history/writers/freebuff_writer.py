"""Writer for converting UnifiedSession to Freebuff format -- 预留占位。

Freebuff 免费版 CLI 的会话由登录后的云端/客户端私有格式管理（本地只落
``~/.config/manicode/projects/<repo>/chats/<id>/`` 的展示性 transcript），
不存在其它引擎那种\"写入一个可被 ``--continue`` 恢复的原生文件\"的等价物：
凭空写一份 ``chat-messages.json`` 不会让 freebuff 认领它，反而会让历史里
出现一个无法恢复的孤儿会话。

因此转换“到” freebuff 在这里明确失败并说明原因，等 headless/ACP 通道
（上游 open issue #947）就绪后再补真实实现。转换“自” freebuff（读）不受
影响，见 :mod:`core.session_history.parsers.freebuff_parser`。
"""

from __future__ import annotations

from typing import Any


def write_freebuff_session(session: Any) -> str:
    """Reserved: converting into Freebuff is not supported (see module doc)."""
    raise NotImplementedError(
        "转换到 freebuff 暂不支持：免费版 CLI 没有 headless 通道，无法把"
        "其它引擎的会话写成可被 freebuff --continue 恢复的格式（预留）。"
    )
