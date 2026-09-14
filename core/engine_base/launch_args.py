"""ca 启动器与原生引擎 CLI 之间的参数约定。"""

from __future__ import annotations

import os
import shutil
from collections.abc import Collection, Mapping

_IS_WINDOWS = os.name == "nt"


def is_native_flag(arg: str) -> bool:
    # 含空白的参数是整段提示词（例如委派传进来的多行指令），不是 flag。
    return len(arg) > 1 and arg.startswith("-") and not any(c.isspace() for c in arg)


def split_passthrough(
    args: list[str], subcommands: Collection[str] = ()
) -> tuple[str, list[str]]:
    """把 ca 不认识的参数分成「首条消息」和「原样交给引擎的参数」。

    只要出现原生 flag 或引擎子命令，就整段透传：``--model opus`` 里的
    ``opus`` 分不清是 flag 的值还是提示词，交给引擎自己解析才不会拆错。
    全是普通词时才拼成首条消息，所以 ``ca claude 修一下登录`` 照常可用。
    """
    if not args:
        return "", []
    if args[0] in subcommands or any(is_native_flag(arg) for arg in args):
        return "", list(args)
    return " ".join(args).strip(), []


def is_batch_shim(command: str, env: Mapping[str, str]) -> bool:
    """*command* 在 Windows 上是否解析成 ``.cmd``/``.bat`` 包装。

    npm 装的 CLI 在 Windows 上是 ``.cmd``，参数要经 cmd.exe 转一手：多行参数
    在换行处被截断，引号里的 ``&``、``|`` 还可能被当成命令执行。多行内容不能
    作为参数传给这类命令。
    """
    if not _IS_WINDOWS:
        return False
    resolved = shutil.which(command, path=env.get("PATH"))
    return resolved is not None and resolved.lower().endswith((".cmd", ".bat"))
