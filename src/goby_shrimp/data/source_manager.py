"""
数据源管理器 - 按市场自动路由 + 故障切换 + 增量缓存
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from .base import DataProvider
from .cache import OHLCVCache
from .symbols import detect_market, normalize_symbol
from .tencent_provider import TencentProvider
from .itick_provider import ITickProvider
from .alphavantage_provider import AlphaVantageProvider
from .akshare_provider import AKShareProvider
from .yfinance_provider import YFinanceProvider
from .stooq_provider import StooqProvider
from .minshare_provider import MinShareProvider
from .tushare_provider import TushareProvider
from ..config import get_settings

logger = logging.getLogger("goby_shrimp.data.source_manager")


class DataSourceManager:
    """
    数据源管理器

    默认优先级:
    - CN: tushare -> akshare -> stooq
    - HK: minshare -> tencent -> akshare -> yfinance -> stooq
    - US: alphavantage -> yfinance -> stooq
    """

    PROVIDER_PRIORITY_BY_MARKET = {
        "cn": ["tushare", "akshare", "stooq"],
        "hk": ["minshare", "tencent", "akshare", "yfinance", "stooq"],
        "us": ["alphavantage", "yfinance", "stooq"],
    }

    def __init__(
        self,
        enable_cache: bool = True,
        cache_path: str | None = None,
    ):
        settings = get_settings()
        resolved_cache_path = cache_path or settings.storage.market_cache_path
        self.enable_cache = enable_cache
        self.cache = OHLCVCache(resolved_cache_path) if enable_cache else None
        self._providers: dict[str, DataProvider] = {}

    def _build_provider(self, name: str) -> DataProvider:
        if name == "tencent":
            return TencentProvider()
        if name == "alphavantage":
            return AlphaVantageProvider()
        if name == "itick":
            return ITickProvider()
        if name == "akshare":
            return AKShareProvider()
        if name == "yfinance":
            return YFinanceProvider()
        if name == "stooq":
            return StooqProvider()
        if name == "minshare":
            return MinShareProvider()
        if name == "tushare":
            return TushareProvider()
        raise ValueError(f"Unknown provider: {name}")

    def _get_provider(self, name: str) -> Optional[DataProvider]:
        if name in self._providers:
            return self._providers[name]
        try:
            provider = self._build_provider(name)
            self._providers[name] = provider
            logger.info(f"✅ Initialized provider: {name}")
            return provider
        except Exception as exc:
            logger.warning(f"⚠️ Failed to init {name}: {exc}")
            return None

    def _normalize_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        working = df.copy()
        working.columns = [str(col).lower() for col in working.columns]
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in working.columns:
                raise ValueError(f"Missing required column: {col}")
            working[col] = pd.to_numeric(working[col], errors="coerce")
        if not isinstance(working.index, pd.DatetimeIndex):
            working.index = pd.to_datetime(working.index)
        return working[required].sort_index()

    def _fetch_from_providers(
        self,
        symbol: str,
        start: str,
        end: Optional[str],
        market: str,
    ) -> Optional[pd.DataFrame]:
        priorities = self.PROVIDER_PRIORITY_BY_MARKET.get(market, self.PROVIDER_PRIORITY_BY_MARKET["us"])
        last_error = None
        for provider_name in priorities:
            provider = self._get_provider(provider_name)
            if provider is None:
                continue
            try:
                logger.info(f"📥 Trying {provider_name} for {symbol}...")
                df = provider.fetch_ohlcv(symbol, start, end)
                normalized = self._normalize_frame(df)
                if normalized.empty:
                    logger.warning(f"⚠️ {provider_name} returned empty data for {symbol}")
                    continue
                logger.info(f"✅ {provider_name} succeeded for {symbol} ({len(normalized)} rows)")
                return normalized
            except Exception as exc:
                last_error = exc
                logger.warning(f"⚠️ {provider_name} failed for {symbol}: {exc}")
        logger.error(f"❌ All providers failed for {symbol}: {last_error}")
        return None

    def fetch_ohlcv(
        self,
        ticker: str,
        start: str,
        end: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        market = detect_market(ticker)
        symbol = normalize_symbol(ticker, market=market)
        end_date = end or datetime.now().strftime("%Y-%m-%d")

        if self.cache is None:
            return self._fetch_from_providers(symbol, start, end_date, market)

        def loader(load_start: str, load_end: str) -> pd.DataFrame | None:
            return self._fetch_from_providers(symbol, load_start, load_end, market)

        return self.cache.fetch_or_load(symbol=symbol, start=start, end=end_date, loader=loader)

    def fetch_latest_price(self, ticker: str) -> Optional[float]:
        quote = self.fetch_latest_quote(ticker)
        if quote is None:
            return None
        return float(quote["price"])

    def fetch_latest_quote(self, ticker: str) -> Optional[dict[str, object]]:
        market = detect_market(ticker)
        if market == "hk":
            minshare = self._get_provider("minshare")
            if minshare is not None and hasattr(minshare, "fetch_latest_quote"):
                try:
                    quote = minshare.fetch_latest_quote(ticker)
                    if quote is not None:
                        return quote
                except Exception as exc:
                    logger.warning(f"⚠️ minshare latest quote failed for {ticker}: {exc}")

        now = datetime.now()
        start = (now - timedelta(days=10)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        df = self.fetch_ohlcv(ticker, start, end)
        if df is not None and not df.empty:
            last_row = df.iloc[-1]
            last_index = df.index[-1]
            as_of = last_index.to_pydatetime().isoformat() if hasattr(last_index, "to_pydatetime") else str(last_index)
            return {
                "price": float(last_row["close"]),
                "as_of": as_of,
            }
        return None

    fetchLatestPrice = fetch_latest_price

    def get_provider_status(self) -> dict:
        status: dict[str, str] = {}
        for market, priorities in self.PROVIDER_PRIORITY_BY_MARKET.items():
            for name in priorities:
                key = f"{market}:{name}"
                status[key] = "ok" if name in self._providers else "not_loaded"
        return status


_source_manager: Optional[DataSourceManager] = None


def get_source_manager() -> DataSourceManager:
    global _source_manager
    if _source_manager is None:
        _source_manager = DataSourceManager()
    return _source_manager


def reset_source_manager(enable_cache: bool = True, cache_path: str | None = None) -> DataSourceManager:
    global _source_manager
    _source_manager = DataSourceManager(enable_cache=enable_cache, cache_path=cache_path)
    return _source_manager
