"""Coverage for the cost table -- 181 lines that had none.

These numbers are the ones the Usage page shows as money, so a wrong rate or
a silently-substituted model is not a cosmetic bug. The behaviours pinned
here are the ones that decide *which* rate a model gets, including the two
fallbacks that can quietly price a model as something it is not.
"""

from __future__ import annotations

import pytest

from core.analytics.pricing import _PRICING, _UNKNOWN, calculate_cost, get_rates


def test_a_known_model_gets_its_own_rates():
    assert (
        get_rates("claude-3-5-haiku-20241022") == _PRICING["claude-3-5-haiku-20241022"]
    )


def test_lookup_ignores_case_and_surrounding_space():
    assert (
        get_rates("  Claude-3-5-Haiku-20241022 ")
        == _PRICING["claude-3-5-haiku-20241022"]
    )


def test_a_provider_prefix_is_stripped():
    # "deepseek-ai/deepseek-chat" and "deepseek-chat" are the same product.
    assert get_rates("deepseek-ai/deepseek-chat") == get_rates("deepseek-chat")


def test_an_alias_resolves_to_the_priced_model():
    assert get_rates("qwen3-coder") == _PRICING["qwen3-coder-plus"]


def test_a_dated_claude_id_falls_back_to_the_undated_one():
    # New date suffixes appear without the table being updated, and pricing
    # does not change with the date.
    undated = next(
        k for k in _PRICING if k.startswith("claude-") and not k[-8:].isdigit()
    )
    assert get_rates(f"{undated}-20260101") == _PRICING[undated]


def test_an_unknown_model_is_priced_as_claude_sonnet():
    # Documented as the intended fallback, and worth pinning because it is
    # silent: an unrecognised model still produces a confident dollar figure
    # rather than an obvious zero or an error.
    assert get_rates("no-such-model-anywhere") == _UNKNOWN


def test_the_suffix_scan_can_match_a_longer_unrelated_id():
    # The last resort matches any id *ending* in a known key, so a vendor
    # prefix that is not a "/" prefix still resolves. Pinned rather than
    # endorsed: it is why an unknown id can quietly get real rates.
    known = next(iter(_PRICING))
    assert get_rates(f"some-vendor-{known}") == _PRICING[known]


# ── the arithmetic ───────────────────────────────────────────────────────────
def test_cost_is_per_million_tokens():
    rates = get_rates("claude-3-5-haiku-20241022")
    assert calculate_cost("claude-3-5-haiku-20241022", 1_000_000, 0) == pytest.approx(
        rates[0]
    )


def test_every_token_class_is_charged_at_its_own_rate():
    model = "claude-3-5-haiku-20241022"
    in_r, out_r, cw_r, cr_r = get_rates(model)

    expected = (in_r + out_r + cw_r + cr_r) / 1_000_000
    assert calculate_cost(model, 1, 1, 1, 1) == pytest.approx(expected)


def test_cache_tokens_default_to_zero():
    model = "claude-3-5-haiku-20241022"

    assert calculate_cost(model, 10, 10) == calculate_cost(model, 10, 10, 0, 0)


def test_a_session_with_no_tokens_costs_nothing():
    assert calculate_cost("claude-3-5-haiku-20241022", 0, 0, 0, 0) == 0.0


def test_the_result_is_rounded_rather_than_carrying_float_noise():
    # Costs are summed across thousands of sessions; unrounded values would
    # accumulate representation error into the displayed total.
    value = calculate_cost("claude-3-5-haiku-20241022", 1, 0)

    assert value == round(value, 8)
