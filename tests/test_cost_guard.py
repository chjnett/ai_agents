import pytest


class TestCostGuard:
    def test_records_cost_and_tokens(self):
        # given
        from src.core.cost_guard import CostGuard
        guard = CostGuard(max_cost_usd=10.0, max_tokens=10000)
        # when
        guard.record("gpt-4o-mini", input_tokens=1000, output_tokens=500)
        # then
        assert guard.total_tokens == 1500
        assert guard.total_cost_usd > 0
        assert guard.is_over_limit() is False
        assert "gpt-4o-mini" in guard.summary()["model_breakdown"]

    def test_limit_exceeded_by_cost_raises(self):
        # given
        from src.core.cost_guard import CostGuard, CostLimitExceededError
        guard = CostGuard(max_cost_usd=0.001, max_tokens=100000)
        # when / then
        with pytest.raises(CostLimitExceededError):
            guard.record("gpt-4o", input_tokens=2000, output_tokens=2000)

    def test_limit_exceeded_by_tokens_raises(self):
        # given
        from src.core.cost_guard import CostGuard, CostLimitExceededError
        guard = CostGuard(max_cost_usd=10.0, max_tokens=100)
        # when / then
        with pytest.raises(CostLimitExceededError):
            guard.record("gpt-4o-mini", input_tokens=60, output_tokens=50)
        assert guard.total_tokens == 110

    def test_supports_cached_input_tokens(self):
        # given
        from src.core.cost_guard import CostGuard
        guard = CostGuard(max_cost_usd=10.0, max_tokens=1000)
        # when
        guard.record(
            "gpt-4o-mini",
            input_tokens=10,
            output_tokens=20,
            cached_input_tokens=30,
        )
        # then
        assert guard.total_tokens == 60

    def test_unknown_model_logs_warning(self, caplog):
        # given
        from src.core.cost_guard import CostGuard
        guard = CostGuard(max_cost_usd=10.0, max_tokens=1000)
        # when
        with caplog.at_level("WARNING"):
            guard.record("unknown-model", input_tokens=10, output_tokens=10)
        # then
        assert "Unknown model" in caplog.text

    def test_summary_has_expected_keys(self):
        # given
        from src.core.cost_guard import CostGuard
        guard = CostGuard(max_cost_usd=1.0, max_tokens=1000)
        # when
        guard.record("gpt-4o-mini", input_tokens=10, output_tokens=20)
        summary = guard.summary()
        # then
        assert "total_cost_usd" in summary
        assert "total_tokens" in summary
        assert "max_cost_usd" in summary
        assert "max_tokens" in summary
        assert "limit_exceeded" in summary
        assert "model_breakdown" in summary
