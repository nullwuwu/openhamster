"""
数据源管理器 - 自动故障切换

按优先级尝试多个数据源，全部失败时返回 None
"""
from __future__ import annotations
import logging
import os
from typing import Optional

import pandas as pd

from .base import DataProvider
from .tencent_provider import TencentProvider
from .itick_provider import ITickProvider
from .alphavantage_provider import AlphaVantageProvider
from .akshare_provider import AKShareProvider
from .yfinance_provider import YFinanceProvider
from .stooq_provider import StooqProvider

logger = logging.getLogger("quant_trader.data.source_manager")


class DataSourceManager:
    """
    数据源管理器
    
    按优先级自动切换数据源:
    1. Tencent - 腾讯财经 (港股)
    2. AlphaVantage - 美股
    3. iTick - 综合数据源 (港股/美股/期货) - 待完善
    4. AkShare - 备用
    5. YFinance - 备用
    6. Stooq - 最后备用
    """
    
    # 优先级配置
    PROVIDER_PRIORITY = [
        "tencent",
        "alphavantage",
        "akshare",
        "yfinance", 
        "stooq",
    ]
    
    def __init__(self):
        """初始化所有数据源"""
        self._providers = {}
        self._init_providers()
    
    def _init_providers(self):
        """初始化所有 provider"""
        for name in self.PROVIDER_PRIORITY:
            try:
                if name == "tencent":
                    self._providers[name] = TencentProvider()
                elif name == "alphavantage":
                    self._providers[name] = AlphaVantageProvider()
                elif name == "akshare":
                    self._providers[name] = AKShareProvider()
                elif name == "yfinance":
                    self._providers[name] = YFinanceProvider()
                elif name == "stooq":
                    self._providers[name] = StooqProvider()
                logger.info(f"✅ Initialized provider: {name}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to init {name}: {e}")
    
    def _is_us_stock(self, ticker: str) -> bool:
        """判断是否为美股"""
        # 美股代码: AAPL, MSFT, GOOGL 等（不含 .HK 后缀）
        return "." not in ticker and ticker.isupper() and len(ticker) <= 5
    
    def _fetch_us_stock(self, ticker: str, start: str, end: Optional[str] = None) -> Optional[pd.DataFrame]:
        """使用 yfinance 获取美股数据"""
        import yfinance as yf
        
        try:
            df = yf.download(ticker, start, end, progress=False)
            if df is not None and not df.empty:
                # 整理格式 - yfinance 返回 MultiIndex 列需要处理
                df = df.reset_index()
                if 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date'])
                    df = df.set_index('Date')
                # 处理列名 (可能是 MultiIndex)
                new_cols = []
                for c in df.columns:
                    if isinstance(c, tuple):
                        new_cols.append(c[0])
                    else:
                        new_cols.append(c)
                df.columns = new_cols
                # 首字母大写
                df.columns = [c.capitalize() if isinstance(c, str) else c for c in df.columns]
                logger.info(f"✅ yfinance succeeded for {ticker} ({len(df)} rows)")
                return df
        except Exception as e:
            logger.warning(f"⚠️ yfinance failed for {ticker}: {e}")
        return None
    
    def fetch_ohlcv(
        self,
        ticker: str,
        start: str,
        end: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """
        获取 OHLCV 数据 - 自动故障切换
        
        Args:
            ticker: 股票代码
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            
        Returns:
            pd.DataFrame or None (所有 provider 都失败)
        """
        # 美股专用处理
        if self._is_us_stock(ticker):
            logger.info(f"📥 Fetching US stock {ticker} via yfinance...")
            df = self._fetch_us_stock(ticker, start, end)
            if df is not None:
                return df
        
        last_error = None
        
        for provider_name in self.PROVIDER_PRIORITY:
            provider = self._providers.get(provider_name)
            
            if provider is None:
                logger.warning(f"⚠️ Provider {provider_name} not available, skipping")
                continue
            
            try:
                logger.info(f"📥 Trying {provider_name} for {ticker}...")
                df = provider.fetch_ohlcv(ticker, start, end)
                
                if df is not None and not df.empty:
                    logger.info(f"✅ {provider_name} succeeded for {ticker} ({len(df)} rows)")
                    return df
                else:
                    logger.warning(f"⚠️ {provider_name} returned empty data for {ticker}")
                    
            except Exception as e:
                last_error = str(e)
                logger.warning(f"⚠️ {provider_name} failed for {ticker}: {e}")
                continue
        
        # 所有 provider 都失败
        logger.error(f"❌ All providers failed for {ticker}: {last_error}")
        return None
    
    def fetch_latest_price(self, ticker: str) -> Optional[float]:
        """
        获取最新价格
        
        Args:
            ticker: 股票代码
            
        Returns:
            float or None
        """
        from datetime import datetime, timedelta
        
        now = datetime.now()
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        
        df = self.fetch_ohlcv(ticker, start, end)
        
        if df is not None and not df.empty:
            return float(df.iloc[-1]["close"])
        
        return None
    
    # 兼容旧名称
    fetchLatestPrice = fetch_latest_price
    
    def get_provider_status(self) -> dict:
        """
        获取各 provider 状态
        
        Returns:
            dict: {provider_name: "ok" / "error" / "not_loaded"}
        """
        status = {}
        
        for name in self.PROVIDER_PRIORITY:
            if name in self._providers:
                status[name] = "ok"
            else:
                status[name] = "not_loaded"
        
        return status


# 全局实例
_source_manager: Optional[DataSourceManager] = None


def get_source_manager() -> DataSourceManager:
    """获取全局数据源管理器实例"""
    global _source_manager
    if _source_manager is None:
        _source_manager = DataSourceManager()
    return _source_manager
