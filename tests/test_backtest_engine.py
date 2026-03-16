from __future__ import annotations

import pandas as pd

from goby_shrimp.backtest.backtest_engine import BacktestEngine


class DummyProvider:
    def fetch_ohlcv(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise AssertionError("fetch_ohlcv should not be called in this test")


class DummyStrategy:
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        return pd.Series([0, 1, 1], index=data.index)

    def count_crossovers(self, data: pd.DataFrame) -> int:
        return 1

    def calculate_param_sensitivity(self, data: pd.DataFrame) -> float:
        return 0.1


def test_backtest_engine_marks_zero_dividend_withholding_as_modeled(monkeypatch) -> None:
    index = pd.to_datetime(["2024-01-01", "2024-12-31", "2025-12-31"])
    data = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.0, 101.0, 102.0],
            "volume": [1000, 1000, 1000],
        },
        index=index,
    )
    engine = BacktestEngine(data_provider=DummyProvider())

    monkeypatch.setattr(engine, "load_data", lambda *args, **kwargs: data)
    monkeypatch.setattr(engine, "_calculate_returns", lambda *_args, **_kwargs: pd.Series([0.0, 0.01, 0.01], index=index))
    monkeypatch.setattr(engine, "_extract_trades", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(engine, "_calc_cagr", lambda *_args, **_kwargs: 0.12)
    monkeypatch.setattr(engine, "_calc_max_drawdown", lambda *_args, **_kwargs: 0.08)
    monkeypatch.setattr(engine, "_calc_sharpe", lambda *_args, **_kwargs: 1.1)

    result = engine.run(ticker="2800.HK", strategy=DummyStrategy(), start_date="2024-01-01", end_date="2025-12-31")

    assert result.assumptions == ["slippage", "commission", "tax", "dividend_withholding"]
