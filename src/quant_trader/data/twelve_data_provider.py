"""
Twelve Data 数据源

基于 Twelve Data API 的数据提供者
文档: https://twelvedata.com/docs
"""
from __future__ import annotations
import logging
import time
from typing import Optional

import pandas as pd
import requests

from .base import DataProvider
from ..config import get_settings

logger = logging.getLogger("quant_trader.data.twelve_data")


class TwelveDataProvider(DataProvider):
    """Twelve Data 数据源"""
    
    name = "twelve_data"
    
    # API 限制: free tier 每分钟 8 次
    MAX_REQUESTS_PER_MINUTE = 8
    REQUEST_INTERVAL = 60 / MAX_REQUESTS_PER_MINUTE  # 7.5 秒
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 Twelve Data 提供者
        
        Args:
            api_key: Twelve Data API Key (默认从环境变量 TWELVE_DATA_API_KEY 获取)
        """
        settings = get_settings()
        self.api_key = api_key or settings.integrations.twelve_data_api_key
        if not self.api_key:
            raise ValueError("Twelve Data API key required. Set TWELVE_DATA_API_KEY env var.")
        
        self.base_url = "https://api.twelvedata.com"
        self._last_request_time = 0
    
    def fetch_ohlcv(
        self, 
        ticker: str, 
        start: str, 
        end: Optional[str] = None
    ) -> pd.DataFrame:
        """从 Twelve Data 获取数据"""
        import datetime
        
        # 速率限制
        self._rate_limit()
        
        # 默认 end_date 为今天
        if end is None:
            end = datetime.datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"📥 [{self.name}] Fetching {ticker} from {start} to {end}")
        
        # 调用 API
        url = f"{self.base_url}/time_series"
        params = {
            "symbol": ticker,
            "interval": "1day",  # 日线
            "start_date": start,
            "end_date": end,
            "apikey": self.api_key,
            "outputsize": 5000,  # 最多5000条
        }
        
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            # 检查 API 错误
            if data.get("status") != "ok":
                error_msg = data.get("message", "Unknown error")
                raise RuntimeError(f"Twelve Data API error: {error_msg}")
            
            # 解析数据
            values = data.get("values", [])
            if not values:
                raise RuntimeError(f"No data returned for {ticker}")
            
            # 转换为 DataFrame
            df = pd.DataFrame(values)
            
            # 标准化格式
            df = self._normalize(df)
            
            logger.info(f"✅ [{self.name}] Loaded {len(df)} rows for {ticker}")
            return df
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Twelve Data request failed: {e}")
    
    def _rate_limit(self):
        """速率限制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_INTERVAL:
            wait = self.REQUEST_INTERVAL - elapsed
            logger.info(f"⏳ [{self.name}] Rate limiting: waiting {wait:.1f}s")
            time.sleep(wait)
        self._last_request_time = time.time()
    
    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化 DataFrame 格式"""
        # 转换日期
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.set_index('datetime')
        
        # 重命名列
        rename = {
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume',
        }
        
        # 只保留需要的列
        for col in rename:
            if col not in df.columns:
                raise ValueError(f"Missing column: {col}")
        
        df = df[list(rename.keys())]
        df.columns = [c.lower() for c in df.columns]
        
        # 转换字符串为数值
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 按日期排序
        df = df.sort_index()
        
        return df
