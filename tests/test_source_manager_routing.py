import os
import sys
from unittest.mock import Mock

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.data.source_manager import DataSourceManager


def _mock_df() -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=5, freq="D")
    return pd.DataFrame(
        {
            "open": [1, 2, 3, 4, 5],
            "high": [1, 2, 3, 4, 5],
            "low": [1, 2, 3, 4, 5],
            "close": [1, 2, 3, 4, 5],
            "volume": [10, 10, 10, 10, 10],
        },
        index=idx,
    )


def test_cn_market_priority_prefers_tushare():
    manager = DataSourceManager(enable_cache=False)
    tushare = Mock()
    tushare.fetch_ohlcv.return_value = _mock_df()

    calls: list[str] = []

    def _get_provider(name: str):
        calls.append(name)
        if name == "tushare":
            return tushare
        return None

    manager._get_provider = _get_provider  # type: ignore[method-assign]
    df = manager.fetch_ohlcv("600519", "2026-01-01", "2026-01-10")
    assert df is not None
    assert not df.empty
    assert calls[0] == "tushare"


def test_fallback_when_primary_fails():
    manager = DataSourceManager(enable_cache=False)
    tushare = Mock()
    tushare.fetch_ohlcv.side_effect = RuntimeError("boom")

    akshare = Mock()
    akshare.fetch_ohlcv.return_value = _mock_df()

    def _get_provider(name: str):
        if name == "tushare":
            return tushare
        if name == "akshare":
            return akshare
        return None

    manager._get_provider = _get_provider  # type: ignore[method-assign]
    df = manager.fetch_ohlcv("600519.SH", "2026-01-01", "2026-01-10")
    assert df is not None
    assert not df.empty
    assert tushare.fetch_ohlcv.call_count == 1
    assert akshare.fetch_ohlcv.call_count == 1


def test_cache_hit_avoids_second_provider_call(tmp_path):
    manager = DataSourceManager(enable_cache=True, cache_path=str(tmp_path / "cache.db"))
    tushare = Mock()
    tushare.fetch_ohlcv.return_value = _mock_df()

    def _get_provider(name: str):
        if name == "tushare":
            return tushare
        return None

    manager._get_provider = _get_provider  # type: ignore[method-assign]
    manager.fetch_ohlcv("600519.SH", "2026-01-01", "2026-01-05")
    manager.fetch_ohlcv("600519.SH", "2026-01-01", "2026-01-05")
    assert tushare.fetch_ohlcv.call_count == 1
