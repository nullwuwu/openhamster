"""
Stooq provider tests.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from goby_shrimp.data import StooqProvider, get_provider


NETWORK_TESTS_ENABLED = os.getenv("RUN_NETWORK_TESTS") == "1"


class TestStooqProvider:
    def test_provider_interface(self):
        provider = StooqProvider()
        assert provider.name == "stooq"
        assert hasattr(provider, "fetch_ohlcv")

    def test_get_provider_factory(self):
        provider = get_provider("stooq")
        assert isinstance(provider, StooqProvider)
        assert provider.name == "stooq"

    @patch("goby_shrimp.data.stooq_provider._fetch_stooq_data")
    def test_hk_ticker_format(self, mock_fetch):
        dates = pd.date_range("2025-01-01", periods=3, freq="D", name="Date")
        mock_fetch.return_value = pd.DataFrame(
            {
                "Open": [100, 101, 102],
                "High": [101, 102, 103],
                "Low": [99, 100, 101],
                "Close": [100, 101, 102],
                "Volume": [1000, 1000, 1000],
            },
            index=dates,
        )

        data = StooqProvider(max_retries=1).fetch_ohlcv("2800.hk", "2025-01-01", "2025-01-10")

        assert isinstance(data, pd.DataFrame)
        assert mock_fetch.call_args.args[0] == "2800.HK"


@pytest.mark.integration
@pytest.mark.skipif(not NETWORK_TESTS_ENABLED, reason="set RUN_NETWORK_TESTS=1 to enable network integration tests")
class TestStooqProviderIntegration:
    def test_fetch_2800hk(self):
        provider = StooqProvider()
        end = datetime.now()
        start = end - timedelta(days=3 * 365)

        data = provider.fetch_ohlcv("2800.HK", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

        assert len(data) > 700
        assert set(["open", "high", "low", "close", "volume"]).issubset(data.columns)
        assert data[["open", "high", "low", "close", "volume"]].isnull().sum().sum() == 0

    def test_fetch_us_stock(self):
        data = StooqProvider().fetch_ohlcv("AAPL", "2025-01-01", "2025-03-01")
        assert len(data) > 30


class TestStooqMock:
    @patch("goby_shrimp.data.stooq_provider._fetch_stooq_data")
    def test_fetch_ohlcv_success(self, mock_fetch):
        dates = pd.date_range("2024-01-01", "2024-01-10", freq="D", name="Date")
        mock_fetch.return_value = pd.DataFrame(
            {
                "Open": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
                "High": [110, 111, 112, 113, 114, 115, 116, 117, 118, 119],
                "Low": [90, 91, 92, 93, 94, 95, 96, 97, 98, 99],
                "Close": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
                "Volume": [1000000] * 10,
            },
            index=dates,
        )

        data = StooqProvider(max_retries=1).fetch_ohlcv("SPY", "2024-01-01", "2024-01-10")

        assert len(data) == 10
        assert "open" in data.columns
        assert "close" in data.columns
        assert isinstance(data.index, pd.DatetimeIndex)

    @patch("goby_shrimp.data.stooq_provider._fetch_stooq_data")
    def test_fetch_ohlcv_empty(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()

        with pytest.raises(RuntimeError, match="failed after"):
            StooqProvider(max_retries=1).fetch_ohlcv("INVALID", "2024-01-01", "2024-01-10")

    @patch("goby_shrimp.data.stooq_provider.requests.get")
    def test_fetch_stooq_data_accepts_lowercase_date_column(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.text = "date,open,high,low,close,volume\n2024-01-02,1,2,0.5,1.5,100\n"
        mock_get.return_value = response

        data = StooqProvider(max_retries=1).fetch_ohlcv("AAPL", "2024-01-01", "2024-01-10")

        assert len(data) == 1
        assert list(data.columns) == ["open", "high", "low", "close", "volume"]
