"""
AKShare 数据源

基于 AKShare 库的数据提供者 (东方财富)
支持港股、日线数据
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import akshare as ak

from .base import DataProvider

logger = logging.getLogger("goby_shrimp.data.akshare")

# AKShare 港股代码转换表
HK_TICKER_MAP = {}


def _convert_hk_ticker(ticker: str) -> str:
    """
    将标准港股代码转换为 AKShare 所需格式
    
    Args:
        ticker: 标准代码，如 "2800.HK", "02800.HK", "2800"
        
    Returns:
        AKShare 所需代码，如 "02800"
    """
    # 去除 .HK 后缀
    ticker = ticker.replace(".HK", "").replace(".hk", "")
    
    # 补齐为 5 位数字
    ticker = ticker.zfill(5)
    
    return ticker


class AKShareProvider(DataProvider):
    """AKShare 数据源 (东方财富)"""
    
    name = "akshare"
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
    
    def fetch_ohlcv(
        self, 
        ticker: str, 
        start: str, 
        end: Optional[str] = None
    ) -> pd.DataFrame:
        """从 AKShare 获取港股数据"""
        logger.info(f"📥 [{self.name}] Fetching {ticker} from {start} to {end}")
        
        # 转换代码格式
        akshare_symbol = _convert_hk_ticker(ticker)
        
        # 转换日期格式
        start_date = self._format_date(start)
        end_date = self._format_date(end) if end else datetime.now().strftime("%Y%m%d")
        
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                data = ak.stock_hk_hist(
                    symbol=akshare_symbol,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date
                )
                
                if data is None or data.empty:
                    last_error = f"No data for {ticker}"
                    logger.warning(f"⚠️ [{self.name}] Attempt {attempt + 1}: {last_error}")
                    continue
                
                # 标准化列名
                df = self._normalize(data)
                
                # 数据校验
                self._validate(df)
                
                logger.info(f"✅ [{self.name}] Loaded {len(df)} rows for {ticker}")
                return df
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"⚠️ [{self.name}] Attempt {attempt + 1} failed: {e}")
        
        raise RuntimeError(f"{self.name} failed after {self.max_retries} attempts: {last_error}")
    
    def _format_date(self, date_str: str) -> str:
        """将 YYYY-MM-DD 转换为 YYYYMMDD"""
        if isinstance(date_str, int):
            return str(date_str)
        
        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]:
            try:
                dt = datetime.strptime(str(date_str), fmt)
                return dt.strftime("%Y%m%d")
            except ValueError:
                continue
        
        raise ValueError(f"Invalid date format: {date_str}")
    
    def _normalize(self, data: pd.DataFrame) -> pd.DataFrame:
        """标准化 DataFrame 格式"""
        # AKShare 返回列名: 日期, 开盘, 收盘, 最高, 最低, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
        rename = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
        }
        
        df = data.rename(columns=rename)
        
        # 只保留需要的列
        required = ["date", "open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        df = df[required]
        
        # 转换日期
        df["date"] = pd.to_datetime(df["date"])
        
        # 转换数值
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # Volume 可能是科学计数法，转为整数
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        
        # 设置索引并排序
        df = df.set_index("date").sort_index()
        
        return df
    
    def _validate(self, df: pd.DataFrame):
        """验证数据完整性"""
        null_count = df[["open", "high", "low", "close", "volume"]].isnull().sum().sum()
        
        if null_count > 0:
            logger.warning(f"⚠️ [{self.name}] Data contains {null_count} null values")
