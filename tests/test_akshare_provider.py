"""
AKShare provider tests.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from openhamster.config import get_settings
from openhamster.data import AKShareProvider, get_provider


NETWORK_TESTS_ENABLED = os.getenv("RUN_NETWORK_TESTS") == "1"


class TestAKShareProvider:
    def test_provider_interface(self):
        provider = AKShareProvider()
        assert provider.name == "akshare"
        assert hasattr(provider, "fetch_ohlcv")

    def test_get_provider_factory(self):
        provider = get_provider("akshare")
        assert isinstance(provider, AKShareProvider)
        assert provider.name == "akshare"

    def test_default_provider_matches_settings(self):
        provider = get_provider()
        assert provider.name == get_settings().data_source.provider

    def test_hk_ticker_conversion(self):
        from openhamster.data.akshare_provider import _convert_hk_ticker

        assert _convert_hk_ticker("2800") == "02800"
        assert _convert_hk_ticker("2800.HK") == "02800"
        assert _convert_hk_ticker("02800") == "02800"
        assert _convert_hk_ticker("5") == "00005"

    def test_normalize_dataframe(self):
        raw = pd.DataFrame(
            {
                "日期": ["2024-01-01", "2024-01-02"],
                "开盘": ["100", "101"],
                "收盘": ["102", "103"],
                "最高": ["105", "106"],
                "最低": ["99", "100"],
                "成交量": ["100000", "120000"],
            }
        )

        normalized = AKShareProvider()._normalize(raw)

        assert list(normalized.columns) == ["open", "high", "low", "close", "volume"]
        assert isinstance(normalized.index, pd.DatetimeIndex)

    @patch("openhamster.data.akshare_provider.ak.stock_hk_hist")
    def test_invalid_ticker(self, mock_stock_hk_hist):
        mock_stock_hk_hist.side_effect = RuntimeError("invalid symbol")

        with pytest.raises(RuntimeError, match="failed after"):
            AKShareProvider(max_retries=1).fetch_ohlcv("INVALID999", "2024-01-01", "2024-01-10")


@pytest.mark.integration
@pytest.mark.skipif(not NETWORK_TESTS_ENABLED, reason="set RUN_NETWORK_TESTS=1 to enable network integration tests")
class TestAKShareProviderIntegration:
    def test_fetch_2800hk(self):
        provider = AKShareProvider()
        end = datetime.now()
        start = end - timedelta(days=3 * 365)

        data = provider.fetch_ohlcv("2800.HK", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

        assert len(data) > 700
        assert set(["open", "high", "low", "close", "volume"]).issubset(data.columns)
        assert data[["open", "high", "low", "close", "volume"]].isnull().sum().sum() == 0

    def test_fetch_another_hk_stock(self):
        data = AKShareProvider().fetch_ohlcv("0700.HK", "2025-01-01", "2025-03-01")
        assert len(data) > 30


class TestProviderRegistry:
    def test_list_providers(self):
        from openhamster.data import _PROVIDERS

        assert "akshare" in _PROVIDERS
        assert "stooq" in _PROVIDERS
        assert "yfinance" in _PROVIDERS
        assert "twelve_data" in _PROVIDERS

    def test_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("unknown_provider")
