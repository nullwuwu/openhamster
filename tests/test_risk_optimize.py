"""
Risk manager and optimization tests.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from openhamster.risk import RiskManager
from openhamster.strategy.signals import Signal


NETWORK_TESTS_ENABLED = os.getenv("RUN_NETWORK_TESTS") == "1"


class TestRiskManager:
    def test_init(self):
        rm = RiskManager(
            max_position_pct=0.6,
            stop_loss_pct=0.08,
            take_profit_pct=0.20,
            max_drawdown_pct=0.15,
        )

        assert rm.max_position_pct == 0.6
        assert rm.stop_loss_pct == 0.08
        assert rm.take_profit_pct == 0.20
        assert rm.max_drawdown_pct == 0.15

    def test_stop_loss_trigger(self):
        rm = RiskManager(stop_loss_pct=0.08)
        context = {
            "position_qty": 1000,
            "avg_cost": 100.0,
            "current_price": 90.0,
            "total_equity": 100000,
            "cash": 10000,
            "max_drawdown_pct": 0,
        }

        assert rm.evaluate(Signal.SELL, context) == Signal.SELL

    def test_take_profit_trigger(self):
        rm = RiskManager(take_profit_pct=0.20)
        context = {
            "position_qty": 1000,
            "avg_cost": 100.0,
            "current_price": 125.0,
            "total_equity": 100000,
            "cash": 10000,
            "max_drawdown_pct": 0,
        }

        assert rm.evaluate(Signal.HOLD, context) == Signal.SELL

    def test_max_drawdown_trigger(self):
        rm = RiskManager(max_drawdown_pct=0.15)
        context = {
            "position_qty": 0,
            "avg_cost": 0,
            "current_price": 0,
            "total_equity": 85000,
            "cash": 85000,
            "max_drawdown_pct": -0.16,
        }

        assert rm.evaluate(Signal.BUY, context) == Signal.HOLD

    def test_position_limit(self):
        rm = RiskManager(max_position_pct=0.6)
        context = {
            "position_qty": 0,
            "avg_cost": 0,
            "current_price": 100.0,
            "total_equity": 100000,
            "cash": 100000,
            "max_drawdown_pct": 0,
        }

        assert rm.evaluate(Signal.BUY, context) == Signal.HOLD

    def test_existing_position_no_buy(self):
        rm = RiskManager()
        context = {
            "position_qty": 1000,
            "avg_cost": 25.0,
            "current_price": 26.0,
            "total_equity": 100000,
            "cash": 74000,
            "max_drawdown_pct": 0,
        }

        assert rm.evaluate(Signal.BUY, context) == Signal.HOLD

    def test_pass_through(self):
        rm = RiskManager()
        context = {
            "position_qty": 0,
            "avg_cost": 0,
            "current_price": 0,
            "total_equity": 100000,
            "cash": 100000,
            "max_drawdown_pct": 0,
        }

        assert rm.evaluate(Signal.BUY, context) == Signal.BUY
        assert rm.evaluate(Signal.SELL, context) == Signal.SELL


@pytest.mark.integration
@pytest.mark.skipif(not NETWORK_TESTS_ENABLED, reason="set RUN_NETWORK_TESTS=1 to enable network integration tests")
class TestResearchIntegration:
    def test_grid_search(self):
        from openhamster.backtest import GridSearchOptimizer

        optimizer = GridSearchOptimizer(
            symbol="2800.HK",
            start_date="2024-01-01",
            end_date="2025-01-01",
            provider_name="stooq",
        )

        df = optimizer.search(short_range=[5, 10], long_range=[20, 30], top_n=3)

        assert not df.empty
        assert "sharpe_ratio" in df.columns

    @pytest.mark.slow
    def test_walk_forward(self):
        from openhamster.backtest import WalkForwardEngine

        engine = WalkForwardEngine(
            symbol="2800.HK",
            train_months=6,
            test_months=2,
            step_months=2,
            provider_name="stooq",
        )

        result = engine.run("2023-01-01", "2025-01-01")

        assert result is not None
        assert result.summary["total_windows"] >= 2
