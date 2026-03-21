"""MinShare 数据源。

统一承接：
- `minishare（港股历史日线 / 实时日线）`
- `tinyshare（2k 积分类基础接口）`

当前第一步只把 `港股历史日线` 接进 `fetch_ohlcv` 主链。
"""
from __future__ import annotations

import importlib
import logging
import time
from datetime import datetime
from typing import Optional

import pandas as pd

from .base import DataProvider
from .symbols import detect_market, normalize_hk_symbol, normalize_tushare_symbol
from ..config import get_settings

logger = logging.getLogger("openhamster.data.minshare")


class MinShareProvider(DataProvider):
    """MinShare 统一数据源。"""

    name = "minshare"

    def __init__(
        self,
        hk_daily_token: Optional[str] = None,
        hk_rt_token: Optional[str] = None,
        two_k_token: Optional[str] = None,
        max_retries: int = 3,
    ):
        settings = get_settings()
        self.hk_daily_token = hk_daily_token or settings.integrations.minshare_hk_daily_token
        self.hk_rt_token = hk_rt_token or settings.integrations.minshare_hk_rt_token
        self.two_k_token = two_k_token or settings.integrations.minshare_2k_token
        self.max_retries = max_retries

    def fetch_ohlcv(
        self,
        ticker: str,
        start: str,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        market = detect_market(ticker)
        if market != "hk":
            raise RuntimeError(f"minshare only supports HK OHLCV right now: {ticker}")
        if not self.hk_daily_token:
            raise ValueError("MINISHARE_HK_DAILY_TOKEN is required for HK daily data")

        module = self._import_minishare()
        ts_code = normalize_tushare_symbol(ticker)
        start_date = self._to_yyyymmdd(start)
        end_date = self._to_yyyymmdd(end) if end else datetime.now().strftime("%Y%m%d")

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"📥 [minshare] Fetching HK daily {ts_code} {start_date}~{end_date}")
                data = module.pro_api(self.hk_daily_token).hk_daily_ms(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                if data is None or data.empty:
                    raise RuntimeError(f"No data for {ts_code}")
                return self._normalize(data)
            except Exception as exc:
                last_error = exc
                logger.warning(f"⚠️ [minshare] Attempt {attempt} failed: {exc}")
                if attempt < self.max_retries:
                    time.sleep(float(attempt))
        raise RuntimeError(f"minshare failed after {self.max_retries} attempts: {last_error}")

    def fetch_hk_trade_calendar(self, start: str, end: str) -> pd.DataFrame:
        if not self.two_k_token:
            raise ValueError("MINISHARE_2K_TOKEN is required for hk_tradecal")
        tinyshare = self._import_tinyshare()
        tinyshare.set_token(self.two_k_token)
        pro = tinyshare.pro_api()
        return pro.hk_tradecal(
            start_date=self._to_yyyymmdd(start),
            end_date=self._to_yyyymmdd(end),
        )

    def fetch_hk_basic(self) -> pd.DataFrame:
        if not self.two_k_token:
            raise ValueError("MINISHARE_2K_TOKEN is required for hk_basic")
        tinyshare = self._import_tinyshare()
        tinyshare.set_token(self.two_k_token)
        pro = tinyshare.pro_api()
        return pro.hk_basic()

    def fetch_hk_rt_daily(self, ticker: str) -> pd.DataFrame:
        if not self.hk_rt_token:
            raise ValueError("MINISHARE_HK_RT_TOKEN is required for HK realtime daily")
        module = self._import_minishare()
        api = module.pro_api(self.hk_rt_token)
        raw_ticker = str(ticker or "").strip().upper()
        if "*" in raw_ticker:
            return api.rt_hk_k_ms(ts_code=raw_ticker)
        direct_ts_code = normalize_tushare_symbol(raw_ticker)
        try:
            return api.rt_hk_k_ms(ts_code=direct_ts_code)
        except Exception as exc:
            # Some realtime endpoints only match wildcard groups reliably.
            prefix = direct_ts_code[:2]
            wildcard = f"{prefix}*.HK"
            data = api.rt_hk_k_ms(ts_code=wildcard)
            if data is None or data.empty:
                raise exc
            working = data.copy()
            if "ts_code" not in working.columns:
                raise exc
            matched = working[working["ts_code"].astype(str).str.upper() == direct_ts_code]
            if matched.empty:
                raise exc
            return matched.reset_index(drop=True)

    def fetch_latest_quote(self, ticker: str) -> Optional[dict[str, object]]:
        if detect_market(ticker) != "hk" or not self.hk_rt_token:
            return None
        data = self.fetch_hk_rt_daily(ticker)
        if data is None or data.empty:
            return None
        latest = self._extract_latest_quote(data)
        if latest is None:
            return None
        return latest

    def fetch_cn_daily_via_2k(self, ticker: str, start: str, end: Optional[str] = None) -> pd.DataFrame:
        if not self.two_k_token:
            raise ValueError("MINISHARE_2K_TOKEN is required for 2k token access")
        tinyshare = self._import_tinyshare()
        tinyshare.set_token(self.two_k_token)
        pro = tinyshare.pro_api()
        data = pro.daily(
            ts_code=normalize_tushare_symbol(ticker),
            start_date=self._to_yyyymmdd(start),
            end_date=self._to_yyyymmdd(end) if end else datetime.now().strftime("%Y%m%d"),
        )
        if data is None or data.empty:
            raise RuntimeError(f"No data for {ticker}")
        return self._normalize(data)

    def _normalize(self, data: pd.DataFrame) -> pd.DataFrame:
        rename = {
            "trade_date": "date",
            "datetime": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "vol": "volume",
            "volume": "volume",
        }
        df = data.rename(columns=rename).copy()
        required = ["date", "open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        df = df[required]
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close", "volume"])
        df = df.set_index("date").sort_index()
        return df

    def _extract_latest_quote(self, data: pd.DataFrame) -> Optional[dict[str, object]]:
        working = data.copy()
        working.columns = [str(column).strip().lower() for column in working.columns]
        if working.empty:
            return None
        row = working.iloc[-1]
        price_columns = ["close", "price", "last", "last_price", "now"]
        price = None
        for column in price_columns:
            if column in working.columns:
                try:
                    price = float(row[column])
                    break
                except Exception:
                    continue
        if price is None:
            return None

        time_columns = ["trade_time", "datetime", "trade_date", "date", "time"]
        as_of = None
        for column in time_columns:
            if column in working.columns:
                value = row[column]
                if pd.notna(value):
                    as_of = str(value)
                    break
        return {"price": price, "as_of": as_of or datetime.now().isoformat()}

    @staticmethod
    def _to_yyyymmdd(date_value: str) -> str:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(str(date_value), fmt).strftime("%Y%m%d")
            except ValueError:
                continue
        raise ValueError(f"Invalid date format: {date_value}")

    @staticmethod
    def _import_minishare():
        try:
            return importlib.import_module("minishare")
        except Exception as exc:
            raise RuntimeError("minishare package is required") from exc

    @staticmethod
    def _import_tinyshare():
        try:
            return importlib.import_module("tinyshare")
        except Exception as exc:
            raise RuntimeError("tinyshare package is required") from exc
