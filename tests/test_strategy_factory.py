import pandas as pd
from goby_shrimp.strategy import (
    get_strategy_factory,
    get_strategy_knowledge_catalog,
    get_strategy_registry,
    strategy_plugin_names,
)
from goby_shrimp.strategy.signals import Signal


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


def test_registry_exposes_plugin_metadata():
    definitions = get_strategy_registry().definitions()
    assert definitions
    assert any(item.description for item in definitions)
    assert "ma_cross" in strategy_plugin_names()
    assert all(item.knowledge_families for item in definitions)


def test_strategy_knowledge_catalog_matches_baselines():
    catalog = get_strategy_knowledge_catalog()
    assert len(catalog) == 5
    families = {item.family_key for item in catalog}
    assert {"trend_following", "mean_reversion", "breakout", "momentum_filter", "volatility_filter"} == families
    registry = get_strategy_registry()
    assert set(registry.get("ma_cross").knowledge_families) == {"trend_following"}
    assert set(registry.get("channel_breakout").knowledge_families) == {"breakout", "volatility_filter"}
