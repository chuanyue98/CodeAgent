# 模型单价（美元 / 每百万 token）。数据外置在包内 model_pricing.json，
# 调价只改数据文件，代码只负责查找。数据来源：Anthropic / Google /
# OpenAI 官方定价页 + CCS model-pricing.ts。

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_DATA_PATH = Path(__file__).with_name("model_pricing.json")
_DATA = json.loads(_DATA_PATH.read_text(encoding="utf-8"))

# { model_name: (input, output, cache_write, cache_read) }
_PRICING: dict[str, tuple[float, float, float, float]] = {
    name: (rates[0], rates[1], rates[2], rates[3])
    for name, rates in _DATA["rates"].items()
}

# 别名：model name → _PRICING 里的规范 key
_ALIASES: dict[str, str] = _DATA["aliases"]

_FREE: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

# Claude 模型的日期后缀：claude-sonnet-4-6-20260101 → claude-sonnet-4-6
_DATE_SUFFIX_RE = re.compile(r"-\d{8}$")

#: 惰性计算的费率表指纹，见 :func:`pricing_fingerprint`。
_PRICING_FINGERPRINT: str | None = None


def pricing_fingerprint() -> str:
    """Returns a stable fingerprint of the rate table.

    The analytics cache is invalidated on its inputs rather than on a timer,
    and the rates are one of those inputs -- editing a price must drop the
    cached costs, not leave them stale until the history happens to change.
    Memoized because the cache consults this on every request.
    """
    global _PRICING_FINGERPRINT
    if _PRICING_FINGERPRINT is None:
        payload = repr((sorted(_PRICING.items()), sorted(_ALIASES.items()))).encode(
            "utf-8"
        )
        _PRICING_FINGERPRINT = hashlib.sha1(payload).hexdigest()[:16]
    return _PRICING_FINGERPRINT


def _strip_provider_prefix(model: str) -> str:
    """去掉 'deepseek-ai/' 之类的 provider 前缀。"""
    idx = model.find("/")
    return model[idx + 1 :] if idx > 0 else model


def _resolve(key: str) -> tuple[float, float, float, float] | None:
    """按 精确命中 → 别名 → 去日期后缀 → 免费档 → 最长后缀匹配 的顺序查价。"""
    if key in _PRICING:
        return _PRICING[key]

    alias = _ALIASES.get(key)
    if alias and alias in _PRICING:
        return _PRICING[alias]

    stripped = _DATE_SUFFIX_RE.sub("", key)
    if stripped != key and stripped in _PRICING:
        return _PRICING[stripped]

    # 免费档 id（OpenCode Zen 等）以 -free 结尾。
    if key.endswith("-free"):
        return _FREE

    # 兜底：id 以已知 key 结尾仍可命中（非 "/" 分隔的 vendor 前缀）。
    # 取最长命中，避免 "some-vendor-glm-4.5-air" 错拿 glm-4.5 的价。
    best_key: str | None = None
    for known_key in _PRICING:
        if key.endswith(known_key) and (
            best_key is None or len(known_key) > len(best_key)
        ):
            best_key = known_key
    if best_key is not None:
        return _PRICING[best_key]

    return None


def get_rates(model: str) -> tuple[float, float, float, float] | None:
    """返回 (input, output, cache_write, cache_read) 美元/百万 token。

    查不到价时返回 None：调用方把这部分 token 记为未定价。拿别的模型的价
    顶上，会把猜测当成确定的金额展示出来。
    """
    return _resolve(_strip_provider_prefix(model).lower().strip())


def is_known_model(model: str) -> bool:
    """模型能否在价目表中查到价格。"""
    return get_rates(model) is not None


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float | None:
    """美元成本；模型查不到价时返回 None。"""
    rates = get_rates(model)
    if rates is None:
        return None
    in_r, out_r, cw_r, cr_r = rates
    cost = (
        input_tokens * in_r
        + output_tokens * out_r
        + cache_creation_tokens * cw_r
        + cache_read_tokens * cr_r
    ) / 1_000_000
    return round(cost, 8)
