"""
Cost guard for session-level token/cost limits.
"""

from __future__ import annotations

import logging
import threading
from copy import deepcopy

logger = logging.getLogger(__name__)


class CostLimitExceededError(Exception):
    """Raised when cost or token limits are exceeded."""


class CostGuard:
    """Track cumulative token usage and estimated USD cost safely."""

    # USD per 1K tokens
    PRICE_PER_1K: dict[str, dict[str, float]] = {
        "claude-opus-4-6": {"input": 0.015, "output": 0.075},
        "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
        "claude-haiku-4-5": {"input": 0.00025, "output": 0.00125},
        "gpt-4o": {"input": 0.005, "output": 0.015},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gemini-2.0-flash": {"input": 0.0, "output": 0.0},
    }

    DEFAULT_PRICE_PER_1K: dict[str, float] = {"input": 0.01, "output": 0.03}

    def __init__(
        self,
        max_cost_usd: float = 1.0,
        max_tokens: int = 500_000,
        total_cost_usd: float = 0.0,
        total_tokens: int = 0,
        model_usage: dict[str, dict[str, float | int]] | None = None,
    ) -> None:
        self.max_cost_usd = max_cost_usd
        self.max_tokens = max_tokens
        self.total_cost_usd = total_cost_usd
        self.total_tokens = total_tokens
        self.model_usage: dict[str, dict[str, float | int]] = model_usage or {}
        self._lock = threading.Lock()

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        *,
        cached_input_tokens: int = 0,
    ) -> None:
        """
        Accumulate one model call and raise if limits are exceeded.

        `cached_input_tokens` is included to support prompt-caching aware pricing later.
        """
        safe_in = max(input_tokens, 0)
        safe_out = max(output_tokens, 0)
        safe_cached = max(cached_input_tokens, 0)

        if model not in self.PRICE_PER_1K:
            logger.warning(
                "CostGuard: Unknown model '%s'. Using default fallback pricing.",
                model,
            )
            price = self.DEFAULT_PRICE_PER_1K
        else:
            price = self.PRICE_PER_1K[model]

        cached_input_price = float(price.get("cached_input", price["input"]))
        call_cost = (
            safe_in * float(price["input"])
            + safe_cached * cached_input_price
            + safe_out * float(price["output"])
        ) / 1000
        call_tokens = safe_in + safe_cached + safe_out

        with self._lock:
            self.total_tokens += call_tokens
            self.total_cost_usd += call_cost

            if model not in self.model_usage:
                self.model_usage[model] = {"tokens": 0, "cost_usd": 0.0}
            self.model_usage[model]["tokens"] += call_tokens
            self.model_usage[model]["cost_usd"] += call_cost

            if self.is_over_limit():
                raise CostLimitExceededError(
                    f"Session limit exceeded: cost=${self.total_cost_usd:.6f}/{self.max_cost_usd}, "
                    f"tokens={self.total_tokens}/{self.max_tokens}"
                )

    def is_over_limit(self) -> bool:
        return self.total_cost_usd >= self.max_cost_usd or self.total_tokens >= self.max_tokens

    def summary(self) -> dict[str, float | int | bool | dict[str, dict[str, float | int]]]:
        with self._lock:
            return {
                "total_cost_usd": round(self.total_cost_usd, 6),
                "total_tokens": self.total_tokens,
                "max_cost_usd": self.max_cost_usd,
                "max_tokens": self.max_tokens,
                "limit_exceeded": self.is_over_limit(),
                "model_breakdown": deepcopy(self.model_usage),
            }
