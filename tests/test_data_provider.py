"""
Data provider tests.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import Mock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from goby_shrimp.data import TwelveDataProvider, YFinanceProvider


class TestDataProvider:
    def test_yfinance_provider_interface(self):
        provider = YFinanceProvider()
        assert provider.name == "yfinance"
        assert hasattr(provider, "fetch_ohlcv")

    def test_twelve_data_provider_interface(self):
        provider = TwelveDataProvider(api_key="test_key")
        assert provider.name == "twelve_data"
        assert hasattr(provider, "fetch_ohlcv")


class TestYFinanceProvider:
    @patch("goby_shrimp.data.yfinance_provider.requests.get")
    def test_fetch_ohlcv_success(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "chart": {
                "result": [
                    {
                        "timestamp": [1704067200, 1704153600],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [100, 101],
                                    "high": [110, 111],
                                    "low": [90, 91],
                                    "close": [105, 106],
                                    "volume": [1000000, 1200000],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }
        mock_get.return_value = mock_response

        data = YFinanceProvider(max_retries=1).fetch_ohlcv("SPY", "2024-01-01", "2024-01-10")

        assert len(data) == 2
        assert list(data.columns) == ["open", "high", "low", "close", "volume"]
        assert isinstance(data.index, pd.DatetimeIndex)

    @patch("goby_shrimp.data.yfinance_provider.requests.get")
    def test_fetch_ohlcv_empty(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {"chart": {"result": None, "error": None}}
        mock_get.return_value = mock_response

        with pytest.raises(RuntimeError, match="failed after"):
            YFinanceProvider(max_retries=1).fetch_ohlcv("INVALID", "2024-01-01", "2024-01-10")

    def test_date_to_timestamp(self):
        provider = YFinanceProvider()
        assert provider._date_to_timestamp("2024-01-01") > 0
        assert provider._date_to_timestamp("2024/01/01") > 0
        assert provider._date_to_timestamp("20240101") > 0


class TestTwelveDataProvider:
    @patch("goby_shrimp.data.twelve_data_provider.requests.get")
    def test_fetch_ohlcv_success(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "ok",
            "values": [
                {
                    "datetime": "2024-01-01",
                    "open": "100",
                    "high": "110",
                    "low": "90",
                    "close": "100",
                    "volume": "1000000",
                },
                {
                    "datetime": "2024-01-02",
                    "open": "101",
                    "high": "111",
                    "low": "91",
                    "close": "101",
                    "volume": "1000000",
                },
            ],
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        provider = TwelveDataProvider(api_key="test_key")
        data = provider.fetch_ohlcv("SPY", "2024-01-01", "2024-01-02")

        assert len(data) == 2
        assert "open" in data.columns
        assert "close" in data.columns
        assert isinstance(data.index, pd.DatetimeIndex)

    @patch("goby_shrimp.data.twelve_data_provider.requests.get")
    def test_fetch_ohlcv_api_error(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"status": "error", "message": "Invalid symbol"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        provider = TwelveDataProvider(api_key="test_key")
        with pytest.raises(RuntimeError, match="API error"):
            provider.fetch_ohlcv("INVALID", "2024-01-01", "2024-01-02")

    def test_requires_api_key(self):
        with pytest.raises(ValueError, match="API key required"):
            TwelveDataProvider(api_key="")
