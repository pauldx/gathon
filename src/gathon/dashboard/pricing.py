"""Model pricing table and cost calculation utilities."""

from __future__ import annotations

MODEL_PRICING: dict[str, dict[str, float]] = {
    "opus": {
        "input": 15 / 1_000_000,
        "output": 75 / 1_000_000,
        "cache_read": 1.5 / 1_000_000,
        "cache_write": 18.75 / 1_000_000,
    },
    "sonnet": {
        "input": 3 / 1_000_000,
        "output": 15 / 1_000_000,
        "cache_read": 0.3 / 1_000_000,
        "cache_write": 3.75 / 1_000_000,
    },
    "haiku": {
        "input": 0.8 / 1_000_000,
        "output": 4 / 1_000_000,
        "cache_read": 0.08 / 1_000_000,
        "cache_write": 1.0 / 1_000_000,
    },
    "gpt-5": {
        "input": 2.5 / 1_000_000,
        "output": 10 / 1_000_000,
        "cache_read": 1.25 / 1_000_000,
        "cache_write": 0.0,
    },
    "gpt-4.1": {
        "input": 2.0 / 1_000_000,
        "output": 8.0 / 1_000_000,
        "cache_read": 0.5 / 1_000_000,
        "cache_write": 0.0,
    },
    "gpt-4.1-mini": {
        "input": 0.4 / 1_000_000,
        "output": 1.6 / 1_000_000,
        "cache_read": 0.1 / 1_000_000,
        "cache_write": 0.0,
    },
    "gpt-4o": {
        "input": 2.5 / 1_000_000,
        "output": 10 / 1_000_000,
        "cache_read": 1.25 / 1_000_000,
        "cache_write": 0.0,
    },
    "gpt-4o-mini": {
        "input": 0.15 / 1_000_000,
        "output": 0.6 / 1_000_000,
        "cache_read": 0.075 / 1_000_000,
        "cache_write": 0.0,
    },
    "gemini-2.5-pro": {
        "input": 1.25 / 1_000_000,
        "output": 10.0 / 1_000_000,
        "cache_read": 0.31 / 1_000_000,
        "cache_write": 0.0,
    },
    "gemini-2.0-flash": {
        "input": 0.1 / 1_000_000,
        "output": 0.4 / 1_000_000,
        "cache_read": 0.025 / 1_000_000,
        "cache_write": 0.0,
    },
    "gemini-1.5-pro": {
        "input": 1.25 / 1_000_000,
        "output": 5.0 / 1_000_000,
        "cache_read": 0.31 / 1_000_000,
        "cache_write": 0.0,
    },
    "gemini-1.5-flash": {
        "input": 0.075 / 1_000_000,
        "output": 0.3 / 1_000_000,
        "cache_read": 0.01875 / 1_000_000,
        "cache_write": 0.0,
    },
    "deepseek-v3": {
        "input": 0.27 / 1_000_000,
        "output": 1.1 / 1_000_000,
        "cache_read": 0.07 / 1_000_000,
        "cache_write": 0.0,
    },
    "deepseek-r1": {
        "input": 0.55 / 1_000_000,
        "output": 2.19 / 1_000_000,
        "cache_read": 0.14 / 1_000_000,
        "cache_write": 0.0,
    },
    "qwen-max": {
        "input": 0.4 / 1_000_000,
        "output": 1.2 / 1_000_000,
        "cache_read": 0.0,
        "cache_write": 0.0,
    },
    "mistral-large": {
        "input": 2.0 / 1_000_000,
        "output": 6.0 / 1_000_000,
        "cache_read": 0.0,
        "cache_write": 0.0,
    },
    "grok-3": {
        "input": 3.0 / 1_000_000,
        "output": 15.0 / 1_000_000,
        "cache_read": 0.0,
        "cache_write": 0.0,
    },
}

DEFAULT_MODEL = "sonnet"

_ALIASES: dict[str, str] = {
    "claude-opus": "opus",
    "claude-sonnet": "sonnet",
    "claude-haiku": "haiku",
    "opus-4": "opus",
    "sonnet-4": "sonnet",
    "haiku-4": "haiku",
    "opus-3": "opus",
    "sonnet-3": "sonnet",
    "haiku-3": "haiku",
    "gpt5": "gpt-5",
    "gpt-4o-mini": "gpt-4o-mini",
    "gemini-flash": "gemini-2.0-flash",
    "gemini-pro": "gemini-2.5-pro",
}


def normalize_model(model: str) -> str:
    m = model.lower().strip()
    # Strip provider prefixes
    for prefix in ("anthropic/", "openai/", "google/", "meta/", "mistralai/"):
        if m.startswith(prefix):
            m = m[len(prefix):]
    # Check exact alias
    if m in _ALIASES:
        return _ALIASES[m]
    # Check if a pricing key is a substring
    for key in MODEL_PRICING:
        if key in m:
            return key
    # Keyword matching
    if "opus" in m:
        return "opus"
    if "sonnet" in m:
        return "sonnet"
    if "haiku" in m:
        return "haiku"
    if "gpt-5" in m or "gpt5" in m:
        return "gpt-5"
    if "4.1-mini" in m or "4o-mini" in m:
        return "gpt-4.1-mini"
    if "gpt-4.1" in m:
        return "gpt-4.1"
    if "gpt-4o" in m:
        return "gpt-4o"
    if "gemini-2.5" in m:
        return "gemini-2.5-pro"
    if "gemini-2.0" in m or "gemini-flash" in m:
        return "gemini-2.0-flash"
    if "deepseek-r1" in m:
        return "deepseek-r1"
    if "deepseek" in m:
        return "deepseek-v3"
    if "mistral" in m:
        return "mistral-large"
    if "grok" in m:
        return "grok-3"
    return DEFAULT_MODEL


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str = DEFAULT_MODEL,
) -> float:
    key = normalize_model(model)
    pricing = MODEL_PRICING.get(key, MODEL_PRICING[DEFAULT_MODEL])
    return input_tokens * pricing["input"] + output_tokens * pricing["output"]


def tokens_to_cost_usd(savings_tokens: int, model: str = DEFAULT_MODEL) -> float:
    key = normalize_model(model)
    pricing = MODEL_PRICING.get(key, MODEL_PRICING[DEFAULT_MODEL])
    return savings_tokens * pricing["input"]
