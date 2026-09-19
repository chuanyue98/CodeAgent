"""ca 启动器与原生引擎 CLI 之间的参数约定。"""

from __future__ import annotations

from collections.abc import Collection


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
