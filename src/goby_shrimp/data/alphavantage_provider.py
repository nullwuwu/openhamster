"""
Alpha Vantage 数据源

提供美股数据
"""
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

from .base import DataProvider
from ..config import get_settings

logger = logging.getLogger("goby_shrimp.data.alphavantage")


class AlphaVantageProvider(DataProvider):
    """
    Alpha Vantage 数据源
    
    免费版: 5次/分钟, 500次/天
    支持: 美股、外汇、加密货币
    """
    
    name = "alphavantage"
    
    def __init__(self, api_key: str = None, max_retries: int = 3):
        settings = get_settings()
        self.api_key = api_key or settings.integrations.alphavantage_api_key
        self.max_retries = max_retries
        self.base_url = "https://www.alphavantage.co/query"
    
    def fetch_ohlcv(
        self,
        ticker: str,
        start: str,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        获取 OHLCV 数据
        
        Args:
            ticker: 股票代码，如 "AAPL", "MSFT"
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            
        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        if not self.api_key:
            raise ValueError("Alpha Vantage API key not set")
        
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": ticker,
            "apikey": self.api_key,
            "outputsize": "compact",  # compact = 最近100天 (免费)
        }
        
        last_error = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"📥 [alphavantage] Fetching {ticker} from {start}")
                
                response = requests.get(self.base_url, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                
                # 检查错误
                if "Error Message" in data:
                    raise ValueError(f"API error: {data.get('Error Message')}")
                if "Note" in data:
                    raise ValueError(f"Rate limit: {data.get('Note')}")
                
                time_series = data.get("Time Series (Daily)", {})
                
                if not time_series:
                    raise ValueError(f"No data for {ticker}")
                
                # 转换为 DataFrame
                records = []
                for date_str, values in time_series.items():
                    records.append(
                        {
                            "date": date_str,
                            "open": float(values["1. open"]),
                            "high": float(values["2. high"]),
                            "low": float(values["3. low"]),
                            "close": float(values["4. close"]),
                            "volume": int(values["5. volume"]),
                        }
                    )
                
                df = pd.DataFrame(records)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                
                # 过滤日期范围
                if start:
                    start_dt = pd.to_datetime(start)
                    df = df[df.index >= start_dt]
                if end:
                    end_dt = pd.to_datetime(end)
                    df = df[df.index <= end_dt]
                
                logger.info(f"✅ [alphavantage] Loaded {len(df)} rows for {ticker}")
                return df
                
            except Exception as e:
                logger.warning(f"⚠️ [alphavantage] Attempt {attempt} failed: {e}")
                last_error = e
                if attempt < self.max_retries:
                    import time
                    time.sleep(2.0 * attempt)
        
        raise RuntimeError(f"{self.name} failed after {self.max_retries} attempts: {last_error}")
    
    def get_quote(self, ticker: str) -> Optional[dict]:
        """获取实时报价"""
        if not self.api_key:
            return None
        
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": ticker,
            "apikey": self.api_key,
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            data = response.json()
            
            quote = data.get("Global Quote", {})
            if quote:
                return {
                    "symbol": quote.get("01. symbol"),
                    "price": float(quote.get("05. price", 0)),
                    "change": float(quote.get("09. change", 0)),
                    "volume": int(quote.get("06. volume", 0)),
                }
        except Exception as e:
            logger.warning(f"⚠️ [alphavantage] Quote failed: {e}")
        
        return None
