"""工具调用预览——要能跟着会话活着到另一个引擎里去。

``args_preview`` 不只是给历史界面看的：每个 writer 都会把它再
``json.loads`` 回去，重建目标引擎自己的参数对象。所以把序列化后的 JSON
从中间一刀切开，切掉的不是"一段参数"，而是整个工具调用——解析必然失败，
writer 退回 ``{}``，接力过去的模型看到的是"我调用了 Bash，没传参数"。
本机 17298 次工具调用里有 60% 超过旧的 200 字符预算，也就是说大多数转换
过去的调用都是这种空壳。

所以预览改成裁**结构里的值**、不动结构本身：哪怕一个 90 KB 的 ``Write``
正文放不下，换过去的引擎仍然看得见改的是哪个文件、跑的是哪条命令。

结果预览另有一条底线：拿不到结果时**不能写成空字符串**。对模型来说空串不是
"这条没带过来"，是"这条命令执行了，返回为空"——它会当真。所以有
:data:`RESULT_NOT_CAPTURED` 这个明说。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.session_history.models import ToolCallSummary

#: 参数预览的字符预算。本机分布 p95≈2.5K、p99≈5.3K，4000 能让 98% 的调用
#: 原样通过；超出的那部分靠裁值保住结构，而不是整条作废。
ARGS_PREVIEW_LIMIT = 4000

#: 结果预览的字符预算。沿用原值——把结果真正搬全是另一件事，这里只保证
#: 裁过的结果不会被读成完整输出。
RESULT_PREVIEW_LIMIT = 200

#: 源引擎的解析器根本没取到结果时，写进目标引擎的占位。必须是一句人话：
#: 模型读到它会重新执行，读到 ``""`` 则会认为命令真的没有输出。
RESULT_NOT_CAPTURED = "[tool result was not carried across the engine handoff — re-run the call if you need its output]"

#: 裁掉内容时留下的记号，读起来必须一眼是"还有"而不是"就这些"。
_CLIP_MARK = "…[+{dropped} chars]"

#: 兜底对象的键名，只在参数结构本身就撑爆预算时才会出现。
_OVERFLOW_KEY = "_truncated_preview"

#: 逐层对半砍值的下限，再小就只剩记号本身了。
_MIN_VALUE_BUDGET = 24


def clip_text(text: str, limit: int) -> str:
    """把 *text* 裁到 *limit*，并明说裁掉了多少。

    返回值可能略长于 *limit*——记号本身要占位置。宁可多这十几个字符，也不
    能让截断后的文本读起来像完整内容。

    Args:
        text: 原文。
        limit: 保留的字符数。

    Returns:
        str: 原文，或裁过并带 ``…[+N chars]`` 记号的文本。
    """
    if limit <= 0:
        return _CLIP_MARK.format(dropped=len(text))
    if len(text) <= limit:
        return text
    return text[:limit] + _CLIP_MARK.format(dropped=len(text) - limit)


def _clip_values(value: Any, budget: int) -> Any:
    """按 *budget* 裁掉结构里每个字符串值，键与嵌套层次原样保留。

    键不裁：``file_path`` / ``command`` 这些名字本身就是"我干了什么"的信号，
    而且短。

    Args:
        value: 任意可 JSON 序列化的值。
        budget: 单个字符串值允许的字符数。

    Returns:
        同构的新值，长字符串已被裁短。
    """
    if isinstance(value, str):
        return clip_text(value, budget)
    if isinstance(value, dict):
        return {key: _clip_values(item, budget) for key, item in value.items()}
    if isinstance(value, list):
        return [_clip_values(item, budget) for item in value]
    return value


def args_preview(value: Any, *, limit: int = ARGS_PREVIEW_LIMIT) -> str:
    """工具调用参数的预览，**保证是能 parse 的 JSON**（或空串）。

    调用方（writer）会无条件把返回值喂给 ``json.loads``，所以这个函数只有两
    种合法产出：空串，或一段合法 JSON。

    Args:
        value: 引擎记下的参数对象，通常是 dict。
        limit: 字符预算。

    Returns:
        str: 合法 JSON 文本；参数为空时返回 ``""``。
    """
    if value is None or value == {} or value == [] or value == "":
        return ""

    try:
        rendered = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        # 不可序列化的参数（引擎写了自定义对象）：退成一段文本，但仍然包在
        # 合法 JSON 里，免得 writer 那边照样炸。
        return json.dumps(clip_text(str(value), limit), ensure_ascii=False)

    if len(rendered) <= limit:
        return rendered

    budget = limit
    while budget >= _MIN_VALUE_BUDGET:
        budget //= 2
        try:
            rendered = json.dumps(_clip_values(value, budget), ensure_ascii=False)
        except (TypeError, ValueError):
            break
        if len(rendered) <= limit:
            return rendered

    # 值已经裁到最小还是超——参数结构本身（成百上千个键）就撑爆了预算。退成
    # 单键对象：依然是合法 JSON，也依然带着原文的头一段。
    room = limit
    while room > 0:
        fallback = json.dumps(
            {_OVERFLOW_KEY: clip_text(rendered, room)}, ensure_ascii=False
        )
        if len(fallback) <= limit:
            return fallback
        room //= 2
    return json.dumps({_OVERFLOW_KEY: ""}, ensure_ascii=False)


def result_preview(value: Any, *, limit: int = RESULT_PREVIEW_LIMIT) -> str:
    """工具结果的预览，裁过就带记号。

    和 :func:`args_preview` 不同，结果是给人和模型读的纯文本，不需要是 JSON。

    Args:
        value: 引擎记下的结果，字符串或可序列化对象。
        limit: 字符预算。

    Returns:
        str: 结果文本；裁过时带 ``…[+N chars]``。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(value)
    return clip_text(text, limit)


def result_for_writer(call: ToolCallSummary) -> str:
    """写进目标引擎的结果文本——拿不到就明说，绝不退化成空串。

    ``result_captured`` 只用来消解**空结果**的歧义（"命令没有输出" vs "我们
    没去取"）。非空的 ``result_preview`` 本身就证明取到过，所以这里不强求两
    者一致：漏设 flag 不应该把一段真实结果抹成一句占位。

    Args:
        call: 要写出的工具调用。

    Returns:
        str: 结果文本，或 :data:`RESULT_NOT_CAPTURED`。
    """
    if call.result_captured or call.result_preview:
        return call.result_preview
    return RESULT_NOT_CAPTURED
