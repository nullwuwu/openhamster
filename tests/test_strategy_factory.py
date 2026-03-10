import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.strategy import get_strategy_factory
from quant_trader.strategy.signals import Signal


def _mock_df(rows: int = 120) -> pd.DataFrame:
    data = {
        "open": [100 + i * 0.1 for i in range(rows)],
        "high": [101 + i * 0.1 for i in range(rows)],
        "low": [99 + i * 0.1 for i in range(rows)],
        "close": [100 + i * 0.1 for i in range(rows)],
        "volume": [1_000_000 for _ in range(rows)],
    }
    idx = pd.date_range("2025-01-01", periods=rows, freq="D")
    return pd.DataFrame(data, index=idx)


def test_factory_create_stream_strategy():
    strategy = get_strategy_factory().create("ma_cross", mode="stream", params={"short_window": 5, "long_window": 20})
    signal = strategy.generate_signal(_mock_df())
    assert signal in {Signal.BUY, Signal.SELL, Signal.HOLD}


def test_factory_create_vectorized_strategy():
    strategy = get_strategy_factory().create("mean_reversion", mode="vectorized")
    series = strategy.generate_signals(_mock_df())
    assert len(series) == 120
    assert set(series.dropna().unique()).issubset({-1, 0, 1})


def test_factory_unknown_strategy():
    try:
        get_strategy_factory().create("unknown_strategy")
        assert False, "should raise ValueError"
    except ValueError:
        assert True
