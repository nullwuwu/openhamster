"""
Tushare 数据源（A股）
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

import pandas as pd

from .base import DataProvider
from .symbols import normalize_cn_symbol
from ..config import get_settings

logger = logging.getLogger("quant_trader.data.tushare")


class TushareProvider(DataProvider):
    """Tushare A 股日线提供者"""

    name = "tushare"

    def __init__(self, token: Optional[str] = None, max_retries: int = 3):
        settings = get_settings()
        self.token = token or settings.integrations.tushare_token
        self.max_retries = max_retries
        if not self.token:
            raise ValueError("Tushare token required. Set TUSHARE_TOKEN env var.")
        try:
            import tushare as ts
        except Exception as exc:
            raise RuntimeError("tushare package is required") from exc
        self._ts = ts
        self._pro = ts.pro_api(self.token)

    def fetch_ohlcv(
        self,
        ticker: str,
        start: str,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        ts_code = normalize_cn_symbol(ticker)
        start_date = self._to_tushare_date(start)
        end_date = self._to_tushare_date(end) if end else datetime.now().strftime("%Y%m%d")

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"📥 [tushare] Fetching {ts_code} {start_date}~{end_date}")
                data = self._pro.daily(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                if data is None or data.empty:
                    raise RuntimeError(f"No data for {ts_code}")
                df = self._normalize(data)
                logger.info(f"✅ [tushare] Loaded {len(df)} rows for {ts_code}")
                return df
            except Exception as exc:
                last_error = exc
                logger.warning(f"⚠️ [tushare] Attempt {attempt} failed: {exc}")
                if attempt < self.max_retries:
                    time.sleep(float(attempt))
        raise RuntimeError(f"tushare failed after {self.max_retries} attempts: {last_error}")

    def fetch_stock_basic(self, list_status: str = "L") -> pd.DataFrame:
        """
        获取股票基础信息
        """
        data = self._pro.stock_basic(
            exchange="",
            list_status=list_status,
            fields="ts_code,symbol,name,area,industry,list_date,market",
        )
        if data is None or data.empty:
            return pd.DataFrame(
                columns=["ts_code", "symbol", "name", "area", "industry", "list_date", "market"]
            )
        return data

    def _normalize(self, data: pd.DataFrame) -> pd.DataFrame:
        rename = {
            "trade_date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "vol": "volume",
        }
        df = data.rename(columns=rename)
        required = ["date", "open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        df = df[required].copy()
        df["date"] = pd.to_datetime(df["date"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = df["volume"] * 100  # vol 单位为手，统一为股
        df = df.set_index("date").sort_index()
        return df

    @staticmethod
    def _to_tushare_date(date_value: str) -> str:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(str(date_value), fmt).strftime("%Y%m%d")
            except ValueError:
                continue
        raise ValueError(f"Invalid date format: {date_value}")
