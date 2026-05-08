from __future__ import annotations

# USD per million tokens
# Format: { model_name: (input_rate, output_rate, cache_write_rate, cache_read_rate) }
# Sources: Anthropic / Google / OpenAI official pages + CCS model-pricing.ts
# Rates marked (0.0, 0.0, ...) = free/experimental tier

_PRICING: dict[str, tuple[float, float, float, float]] = {
    # ── Claude 3.x ────────────────────────────────────────────────────────────
    "claude-3-haiku-20240307": (0.25, 1.25, 0.3, 0.03),
    "claude-3-5-haiku-20241022": (0.8, 4.0, 1.0, 0.08),
    "claude-3-5-haiku-latest": (0.8, 4.0, 1.0, 0.08),
    "claude-3-5-sonnet-20240620": (3.0, 15.0, 3.75, 0.3),
    "claude-3-5-sonnet-20241022": (3.0, 15.0, 3.75, 0.3),
    "claude-3-5-sonnet-latest": (3.0, 15.0, 3.75, 0.3),
    "claude-3-7-sonnet-20250219": (3.0, 15.0, 3.75, 0.3),
    "claude-3-7-sonnet-latest": (3.0, 15.0, 3.75, 0.3),
    "claude-3-opus-20240229": (15.0, 75.0, 18.75, 1.5),
    "claude-3-opus-latest": (15.0, 75.0, 18.75, 1.5),
    # ── Claude 4.x Haiku ──────────────────────────────────────────────────────
    "claude-haiku-4-5-20251001": (1.0, 5.0, 1.25, 0.1),
    "claude-haiku-4-5": (1.0, 5.0, 1.25, 0.1),
    # ── Claude 4.x Sonnet ─────────────────────────────────────────────────────
    "claude-4-sonnet-20250514": (3.0, 15.0, 3.75, 0.3),
    "claude-sonnet-4-20250514": (3.0, 15.0, 3.75, 0.3),
    "claude-sonnet-4": (3.0, 15.0, 3.75, 0.3),
    "claude-sonnet-4-5-20250929": (3.0, 15.0, 3.75, 0.3),
    "claude-sonnet-4-5": (3.0, 15.0, 3.75, 0.3),
    "claude-sonnet-4-5-thinking": (3.0, 15.0, 3.75, 0.3),
    "claude-sonnet-4-6": (3.0, 15.0, 3.75, 0.3),
    "claude-sonnet-4-6-thinking": (3.0, 15.0, 3.75, 0.3),
    # ── Claude 4.x Opus ──────────────────────────────────────────────────────
    "claude-4-opus-20250514": (15.0, 75.0, 18.75, 1.5),
    "claude-opus-4-20250514": (15.0, 75.0, 18.75, 1.5),
    "claude-opus-4": (15.0, 75.0, 18.75, 1.5),
    "claude-opus-4-1": (15.0, 75.0, 18.75, 1.5),
    "claude-opus-4-1-20250805": (15.0, 75.0, 18.75, 1.5),
    "claude-opus-4-5-20251101": (5.0, 25.0, 6.25, 0.5),  # new pricing tier
    "claude-opus-4-5": (5.0, 25.0, 6.25, 0.5),
    "claude-opus-4-5-thinking": (5.0, 25.0, 6.25, 0.5),
    "claude-opus-4-6": (5.0, 25.0, 6.25, 0.5),
    "claude-opus-4-6-thinking": (5.0, 25.0, 6.25, 0.5),
    "claude-opus-4-7": (5.0, 25.0, 6.25, 0.5),
    # ── Google Gemini ─────────────────────────────────────────────────────────
    "gemini-2.5-pro": (1.25, 10.0, 0.0, 0.3125),
    "gemini-2.5-flash": (0.3, 2.5, 0.0, 0.075),  # updated from CCS
    "gemini-2.5-flash-lite": (0.1, 0.4, 0.0, 0.025),
    "gemini-2.5-flash-preview": (0.3, 2.5, 0.0, 0.075),
    "gemini-2.0-flash": (0.1, 0.4, 0.0, 0.025),
    "gemini-2.0-flash-exp": (0.0, 0.0, 0.0, 0.0),
    "gemini-1.5-pro": (3.5, 10.5, 0.0, 0.0),
    "gemini-1.5-flash": (0.075, 0.3, 0.0, 0.0),
    "gemini-1.5-flash-8b": (0.0375, 0.15, 0.0, 0.0),
    # Gemini 3 — official pricing ≤200k ctx
    "gemini-3-pro": (2.0, 12.0, 0.0, 0.0),
    "gemini-3-pro-preview": (2.0, 12.0, 0.0, 0.0),
    "gemini-3-pro-high": (4.0, 18.0, 0.0, 0.0),  # >200k ctx variant
    # ── OpenAI / Codex ────────────────────────────────────────────────────────
    "gpt-4o": (2.5, 10.0, 0.0, 1.25),
    "gpt-4o-2024-08-06": (2.5, 10.0, 0.0, 1.25),
    "gpt-4o-2024-11-20": (2.5, 10.0, 0.0, 1.25),
    "gpt-4o-mini": (0.15, 0.6, 0.0, 0.075),
    "gpt-4.1": (2.0, 8.0, 0.0, 0.5),
    "gpt-4.1-mini": (0.4, 1.6, 0.0, 0.1),
    "gpt-4.1-nano": (0.1, 0.4, 0.0, 0.025),
    "gpt-4.5-preview": (75.0, 150.0, 0.0, 37.5),
    "gpt-3.5-turbo": (1.5, 2.0, 0.0, 0.0),
    "gpt-3.5-turbo-0125": (0.5, 1.5, 0.0, 0.0),
    "o1": (15.0, 60.0, 0.0, 7.5),
    "o1-preview": (15.0, 60.0, 0.0, 7.5),
    "o1-mini": (3.0, 12.0, 0.0, 1.5),
    "o3-mini": (1.1, 4.4, 0.0, 0.55),
    "gpt-5": (1.25, 10.0, 0.0, 0.125),
    "gpt-5-chat": (1.25, 10.0, 0.0, 0.125),
    "gpt-5-codex": (1.25, 10.0, 0.0, 0.125),
    "gpt-5-mini": (0.25, 2.0, 0.0, 0.025),
    "gpt-5-nano": (0.05, 0.4, 0.0, 0.005),
    # GPT-5.x Codex CLI variants (internal versioning used by openai/codex)
    "gpt-5.1-codex-mini": (1.5, 6.0, 0.0, 0.375),
    "gpt-5.4": (1.25, 10.0, 0.0, 0.125),
    "gpt-5.4-mini": (0.25, 2.0, 0.0, 0.025),
    "gpt-5.5": (1.25, 10.0, 0.0, 0.125),
    "codex-mini-latest": (1.5, 6.0, 0.0, 0.375),
    # ── GLM / Zhipu AI ────────────────────────────────────────────────────────
    "glm-5": (1.0, 3.2, 0.0, 0.2),
    "glm-4.7": (0.4, 1.5, 0.0, 0.2),
    "glm-4.7-flashx": (0.4, 1.5, 0.0, 0.2),
    "glm-4.6": (0.35, 1.5, 0.0, 0.175),
    "glm-4.6-cc-max": (0.35, 1.5, 0.0, 0.175),
    "glm-4.5": (0.35, 1.55, 0.0, 0.175),
    "glm-4.5-air": (0.13, 0.85, 0.0, 0.025),
    # ── Kimi / Moonshot AI ────────────────────────────────────────────────────
    "kimi-k2.5": (0.6, 3.0, 0.0, 0.1),
    "kimi-k2.5-free": (0.0, 0.0, 0.0, 0.0),
    "kimi-for-coding": (0.6, 2.5, 0.0, 0.15),
    "kimi-k2-0905-preview": (0.6, 2.5, 0.0, 0.15),
    "kimi-k2-turbo-preview": (1.15, 8.0, 0.0, 0.15),
    "kimi-k2-thinking": (0.6, 2.5, 0.0, 0.15),
    "kimi-k2": (0.6, 2.5, 0.0, 0.15),
    "moonshot-v1-8k": (0.2, 2.0, 0.0, 0.0),
    "moonshot-v1-32k": (1.0, 3.0, 0.0, 0.0),
    "moonshot-v1-128k": (2.0, 5.0, 0.0, 0.0),
    # ── MiniMax ───────────────────────────────────────────────────────────────
    "minimax-m2.5": (0.3, 1.2, 0.375, 0.03),
    "minimax-m2.5-free": (0.0, 0.0, 0.0, 0.0),
    "minimax-m2.5-lightning": (0.6, 2.4, 0.375, 0.03),
    "minimax-m2.1": (0.3, 1.2, 0.375, 0.03),
    "minimax-m2": (0.3, 1.2, 0.375, 0.03),
    # ── Qwen / Alibaba ────────────────────────────────────────────────────────
    "qwen3-max": (1.2, 6.0, 1.2, 0.24),
    "qwen3-max-preview": (1.2, 6.0, 1.2, 0.24),
    "qwen3.5-plus": (0.4, 2.4, 0.4, 0.08),
    "qwen3.6-plus": (0.4, 2.4, 0.4, 0.08),
    "qwen3.6-plus-free": (0.0, 0.0, 0.0, 0.0),
    "qwen3.5-flash": (0.1, 0.4, 0.1, 0.02),
    "qwen3-coder-plus": (1.0, 5.0, 1.0, 0.2),
    "qwen3-coder-flash": (0.3, 1.5, 0.3, 0.06),
    # ── DeepSeek ─────────────────────────────────────────────────────────────
    "deepseek-chat": (0.27, 1.1, 0.0, 0.07),
    "deepseek-v3": (0.27, 1.1, 0.0, 0.07),
    "deepseek-v3.2": (0.27, 1.1, 0.0, 0.07),
    "deepseek-reasoner": (0.55, 2.19, 0.0, 0.14),
    "deepseek-coder": (0.14, 0.28, 0.0, 0.0),
    # ── Mistral ───────────────────────────────────────────────────────────────
    "mistral-large-latest": (2.0, 6.0, 0.0, 0.0),
    "mistral-medium-latest": (2.7, 8.1, 0.0, 0.0),
    "mistral-small-latest": (0.2, 0.6, 0.0, 0.0),
    "codestral-latest": (0.3, 0.9, 0.0, 0.0),
    # ── Nemotron ─────────────────────────────────────────────────────────────
    "nemotron-3-super-free": (0.0, 0.0, 0.0, 0.0),
    # ── MiMo ─────────────────────────────────────────────────────────────────
    "mimo-v2-omni-free": (0.0, 0.0, 0.0, 0.0),
    "mimo-v2-pro-free": (0.0, 0.0, 0.0, 0.0),
}

# Aliases: model name → canonical key in _PRICING (from CCS MODEL_PRICING_ALIASES)
_ALIASES: dict[str, str] = {
    "gemini-3-flash-preview": "gemini-2.5-flash",
    "gemini-3-flash-preview-customtools": "gemini-2.5-flash",
    "gemini-3.1-pro-preview": "gemini-3-pro-preview",
    "gemini-3.1-flash-preview": "gemini-2.5-flash",
    "gemini-3-1-pro-preview": "gemini-3-pro-preview",
    "gemini-3-1-flash-preview": "gemini-2.5-flash",
    "qwen3-coder": "qwen3-coder-plus",
    "qwen3-235b": "qwen3-max",
    "deepseek-v3.2": "deepseek-chat",
}

# Unknown model fallback — CCS uses Claude Sonnet pricing
_UNKNOWN: tuple[float, float, float, float] = (3.0, 15.0, 3.75, 0.3)


def _strip_provider_prefix(model: str) -> str:
    """Remove provider prefix like 'deepseek-ai/' or 'minimaxai/'."""
    idx = model.find("/")
    return model[idx + 1 :] if idx > 0 else model


def get_rates(model: str) -> tuple[float, float, float, float]:
    """Return (input, output, cache_write, cache_read) USD per million tokens."""
    key = _strip_provider_prefix(model).lower().strip()

    # Direct lookup
    if key in _PRICING:
        return _PRICING[key]

    # Alias lookup
    alias = _ALIASES.get(key)
    if alias and alias in _PRICING:
        return _PRICING[alias]

    # Strip date suffix for Claude models: claude-sonnet-4-6-20260101 → claude-sonnet-4-6
    import re

    stripped = re.sub(r"-\d{8}$", "", key)
    if stripped != key and stripped in _PRICING:
        return _PRICING[stripped]

    # Partial prefix scan (narrow: only exact-suffix match to avoid false positives)
    for known_key, rates in _PRICING.items():
        if key.endswith(known_key):
            return rates

    return _UNKNOWN


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    in_r, out_r, cw_r, cr_r = get_rates(model)
    cost = (
        input_tokens * in_r
        + output_tokens * out_r
        + cache_creation_tokens * cw_r
        + cache_read_tokens * cr_r
    ) / 1_000_000
    return round(cost, 8)
