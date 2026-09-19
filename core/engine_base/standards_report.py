"""``ca <engine>`` 启动时，规范到底有没有到达引擎。

注入通道每个引擎各不相同（Claude 走系统提示文件、Codex 走 config 覆盖、
OpenCode 走环境变量、Antigravity 没有），"没注入成功"的原因也各不相同
（引擎没有这条通道 / Windows 的 .cmd 包装吞掉了多行参数 / 环境变量不可合并）。
此前这些分支要么只写 logger、要么各写各的提示，用户看不到统一结论。

这个模块只做一件事：把上述事实收成一条用户可见的状态行。
判定逻辑集中在这里，引擎只负责提供事实——只有引擎自己知道本次是否被跳过。
"""

from __future__ import annotations

import sys
from enum import Enum

from core.engine_registry import get_spec
from core.i18n import t


class StandardsDelivery(str, Enum):
    """规范在一次启动里的最终去向。"""

    #: 本次启动注入了规范。
    INJECTED = "injected"
    #: 用户级配置（``ca sync``）已经带着规范，引擎自己就会加载。
    VIA_USER_CONFIG = "via_user_config"
    #: 该引擎根本没有 system-prompt 通道。
    UNSUPPORTED = "unsupported"
    #: 有通道，但本次启动主动跳过（Windows 的 .cmd 包装）。
    SKIPPED = "skipped"
    #: 尝试注入但失败了（环境变量不可合并）。
    FAILED = "failed"


def _user_config_file(engine_key: str) -> str:
    """该引擎用户级规范文件的路径；查不到时返回空串。

    ``sync_service`` 在模块级 import 了 ``core.engine_base``，所以这里只能
    延迟 import，否则 ``engine_base`` 与 ``services`` 之间会形成环。
    """
    from core.services.sync_service import engine_targets

    target = engine_targets().get(engine_key)
    return str(target.memory_file) if target is not None else ""


def report_standards_delivery(
    engine_key: str,
    display_name: str,
    *,
    synced: bool = False,
    skip_reason: str = "",
    failure: str = "",
) -> StandardsDelivery:
    """判定并打印一行规范注入状态，返回判定结果。

    判定顺序即语义：``synced`` 最优先——规范已经在用户级文件里，引擎自己会
    加载，本次注不注入都不影响结果；其次才是"这个引擎没有该通道"、被动跳过、
    注入失败。

    引擎有没有通道由 ``core.engine_registry`` 声明，这里不接收调用方传入——
    否则每个启动脚本都得自己再说一遍，说错了也没人发现。

    输出走 **stderr**：``ca codex -ni`` 与 ``ca opencode run`` 的 stdout 是
    机器可读的 JSON，不能被这行诊断信息污染。
    """
    spec = get_spec(engine_key)
    channel_key = spec.standards_channel if spec is not None else ""

    if synced:
        delivery = StandardsDelivery.VIA_USER_CONFIG
        print(
            t(
                "standards.via_user_config",
                engine=display_name,
                path=_user_config_file(engine_key),
            ),
            file=sys.stderr,
        )
    elif not channel_key:
        delivery = StandardsDelivery.UNSUPPORTED
        print(t("standards.unsupported", engine=display_name), file=sys.stderr)
        print(
            t(
                "standards.unsupported_hint",
                engine=engine_key,
                path=_user_config_file(engine_key),
            ),
            file=sys.stderr,
        )
    elif skip_reason:
        delivery = StandardsDelivery.SKIPPED
        print(
            t("standards.skipped", engine=display_name, reason=skip_reason),
            file=sys.stderr,
        )
    elif failure:
        delivery = StandardsDelivery.FAILED
        print(
            t("standards.failed", engine=display_name, reason=failure),
            file=sys.stderr,
        )
    else:
        delivery = StandardsDelivery.INJECTED
        print(
            t("standards.injected", engine=display_name, channel=t(channel_key)),
            file=sys.stderr,
        )
    return delivery
