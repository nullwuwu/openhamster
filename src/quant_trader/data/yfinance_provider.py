"""
YFinance 数据源

基于 yfinance 的数据提供者
"""
from __future__ import annotations
import logging
from typing import Optional

import pandas as pd
import yfinance as yf

from .base import DataProvider

logger = logging.getLogger("quant_trader.data.yfinance")


class YFinanceProvider(DataProvider):
    """yfinance 数据源"""
    
    name = "yfinance"
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
    
    def fetch_ohlcv(
        self, 
        ticker: str, 
        start: str, 
        end: Optional[str] = None
    ) -> pd.DataFrame:
        """从 yfinance 获取数据"""
        import time
        
        logger.info(f"📥 [{self.name}] Fetching {ticker} from {start} to {end}")
        
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                data = yf.download(
                    ticker, 
                    start=start, 
                    end=end, 
                    progress=False,
                )
                
                if data.empty:
                    last_error = f"No data for {ticker}"
                    logger.warning(f"⚠️ [{self.name}] Attempt {attempt + 1}: {last_error}")
                    time.sleep(5 * (attempt + 1))
                    continue
                
                # 标准化列名
                data = self._normalize_columns(data)
                
                logger.info(f"✅ [{self.name}] Loaded {len(data)} rows for {ticker}")
                return data
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"⚠️ [{self.name}] Attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(5 * (attempt + 1))
        
        raise RuntimeError(f"{self.name} failed after {self.max_retries} attempts: {last_error}")
    
    def _normalize_columns(self, data: pd.DataFrame) -> pd.DataFrame:
        """标准化列名（处理 MultiIndex）"""
        # yfinance 返回可能有多层列名
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        
        # 转为小写以统一格式
        data.columns = [c.lower() for c in data.columns]
        
        # 确保有需要的列
        required = ['open', 'high', 'low', 'close', 'volume']
        for col in required:
            if col not in data.columns:
                raise ValueError(f"Missing required column: {col}")
        
        return data
