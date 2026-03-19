"""
Cost guard for session-level token/cost limits.
"""

from __future__ import annotations


class CostGuard:
    """Track cumulative token usage and estimated USD cost."""

    # USD per 1K tokens
    PRICE_PER_1K: dict[str, dict[str, float]] = {
        "claude-opus-4-6": {"input": 0.015, "output": 0.075},
        "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
        "claude-haiku-4-5": {"input": 0.00025, "output": 0.00125},
        "gpt-4o": {"input": 0.005, "output": 0.015},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gemini-2.0-flash": {"input": 0.0, "output": 0.0},
    }

    def __init__(
        self,
        max_cost_usd: float = 1.0,
        max_tokens: int = 500_000,
        total_cost_usd: float = 0.0,
        total_tokens: int = 0,
    ) -> None:
        self.max_cost_usd = max_cost_usd
        self.max_tokens = max_tokens
        self.total_cost_usd = total_cost_usd
        self.total_tokens = total_tokens

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        """Accumulate usage from one model call."""
        safe_in = max(input_tokens, 0)
        safe_out = max(output_tokens, 0)

        price = self.PRICE_PER_1K.get(model, {"input": 0.01, "output": 0.03})
        cost = (safe_in * price["input"] + safe_out * price["output"]) / 1000

        self.total_tokens += safe_in + safe_out
        self.total_cost_usd += cost

    def is_over_limit(self) -> bool:
        return self.total_cost_usd >= self.max_cost_usd or self.total_tokens >= self.max_tokens

    def summary(self) -> dict[str, float | int | bool]:
        return {
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_tokens": self.total_tokens,
            "max_cost_usd": self.max_cost_usd,
            "max_tokens": self.max_tokens,
            "limit_exceeded": self.is_over_limit(),
        }


'''
테스트 명령어들
     .venv/bin/python3 -m pytest -v
    .venv/bin/python3 test_manual.py
    .venv/bin/python3 test_manual.py --workflow
'''