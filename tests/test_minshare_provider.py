from __future__ import annotations

import os
import sys
import types

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from openhamster.data.minshare_provider import MinShareProvider


def test_requires_hk_daily_token():
    provider = MinShareProvider(hk_daily_token="")
    provider.hk_daily_token = ""
    with pytest.raises(ValueError, match="MINISHARE_HK_DAILY_TOKEN"):
        provider.fetch_ohlcv("2800.HK", "2026-03-01", "2026-03-17")


def test_fetch_ohlcv_normalizes_minishare_payload(monkeypatch):
    frame = pd.DataFrame(
        {
            "trade_date": ["20260303", "20260304"],
            "open": [25.1, 25.2],
            "high": [25.4, 25.5],
            "low": [24.9, 25.0],
            "close": [25.3, 25.4],
            "vol": [1000, 1100],
        }
    )

    class _FakePro:
        def __init__(self, token: str):
            self.token = token

        def hk_daily_ms(self, *, ts_code: str, start_date: str, end_date: str):
            assert ts_code == "02800.HK"
            assert start_date == "20260301"
            assert end_date == "20260317"
            return frame

    fake_module = types.SimpleNamespace(pro_api=lambda token: _FakePro(token))
    monkeypatch.setattr("openhamster.data.minshare_provider.importlib.import_module", lambda name: fake_module)

    provider = MinShareProvider(hk_daily_token="daily-token")
    data = provider.fetch_ohlcv("2800.HK", "2026-03-01", "2026-03-17")

    assert len(data) == 2
    assert list(data.columns) == ["open", "high", "low", "close", "volume"]
    assert str(data.index[0].date()) == "2026-03-03"


def test_fetch_latest_quote_uses_rt_payload(monkeypatch):
    frame = pd.DataFrame(
        {
            "trade_time": ["2026-03-17 10:30:00"],
            "price": [25.88],
        }
    )

    class _FakePro:
        def __init__(self, token: str):
            self.token = token

        def rt_hk_k_ms(self, *, ts_code: str):
            assert ts_code == "02800.HK"
            return frame

    fake_module = types.SimpleNamespace(pro_api=lambda token: _FakePro(token))
    monkeypatch.setattr("openhamster.data.minshare_provider.importlib.import_module", lambda name: fake_module)

    provider = MinShareProvider(hk_rt_token="rt-token")
    quote = provider.fetch_latest_quote("2800.HK")

    assert quote is not None
    assert quote["price"] == 25.88
    assert quote["as_of"] == "2026-03-17 10:30:00"


def test_fetch_latest_quote_falls_back_to_wildcard_and_filters(monkeypatch):
    wildcard_frame = pd.DataFrame(
        {
            "ts_code": ["02800.HK", "02801.HK"],
            "trade_time": ["2026-03-17 15:30:00", "2026-03-17 15:30:00"],
            "close": [26.32, 20.11],
        }
    )

    class _FakePro:
        def __init__(self, token: str):
            self.token = token

        def rt_hk_k_ms(self, *, ts_code: str):
            if ts_code == "02800.HK":
                raise RuntimeError("未找到匹配的数据")
            assert ts_code == "02*.HK"
            return wildcard_frame

    fake_module = types.SimpleNamespace(pro_api=lambda token: _FakePro(token))
    monkeypatch.setattr("openhamster.data.minshare_provider.importlib.import_module", lambda name: fake_module)

    provider = MinShareProvider(hk_rt_token="rt-token")
    quote = provider.fetch_latest_quote("2800.HK")

    assert quote is not None
    assert quote["price"] == 26.32
    assert quote["as_of"] == "2026-03-17 15:30:00"
