"""
Data Provider 抽象层

统一的数据源接口，支持多种数据源插拔式切换
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd


class DataProvider(ABC):
    """数据源抽象基类"""
    
    name: str = "base"
    
    @abstractmethod
    def fetch_ohlcv(
        self, 
        ticker: str, 
        start: str, 
        end: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取 OHLCV 数据
        
        Args:
            ticker: 股票代码 (e.g., "SPY", "AAPL")
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD), 默认今天
            
        Returns:
            pd.DataFrame with columns: [Open, High, Low, Close, Volume]
            index: DatetimeIndex
            
        Raises:
            Exception: 数据获取失败时抛出
        """
        pass
    
    def close(self):
        """关闭连接（可选实现）"""
        pass

    def fetch_latest_quote(self, ticker: str) -> Optional[dict[str, object]]:
        """获取最新报价（可选实现）。"""
        return None
