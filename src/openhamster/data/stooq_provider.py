"""
Stooq 数据源

直接使用 Stooq API 获取数据，替代 pandas_datareader
国际数据源，稳定可靠
"""
from __future__ import annotations
import logging
from io import StringIO
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

from .base import DataProvider

logger = logging.getLogger("openhamster.data.stooq")


def _fetch_stooq_data(symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """直接获取 Stooq 数据，兼容大小写列名和异常 CSV。"""
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    url = f"https://stooq.com/q/d/l/?s={symbol}&d1={start_str}&d2={end_str}"

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    payload = response.text.strip()
    if not payload or payload.lower().startswith("no data"):
        return pd.DataFrame()

    df = pd.read_csv(StringIO(payload))
    if df is None or df.empty:
        return pd.DataFrame()

    normalized_columns = {str(column): str(column).strip().lower() for column in df.columns}
    df = df.rename(columns=normalized_columns)
    if "date" not in df.columns:
        first_column = next(iter(df.columns), "")
        if str(first_column).strip().lower() != "date":
            raise ValueError(f"Unexpected Stooq columns: {list(df.columns)}")
        df = df.rename(columns={first_column: "date"})

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date").sort_index()
    return df


class StooqProvider(DataProvider):
    """Stooq 数据源"""
    
    name = "stooq"
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
    
    def fetch_ohlcv(
        self, 
        ticker: str, 
        start: str, 
        end: Optional[str] = None
    ) -> pd.DataFrame:
        """从 Stooq 获取数据"""
        logger.info(f"📥 [{self.name}] Fetching {ticker} from {start} to {end}")
        
        # 转换日期格式
        start_date = self._format_date(start)
        end_date = self._format_date(end) if end else datetime.now().strftime("%Y-%m-%d")
        
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Stooq 需要大写代码
                ticker_upper = ticker.upper()

                # 直接使用 Stooq API
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")

                data = _fetch_stooq_data(ticker_upper, start_dt, end_dt)

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
        """确保日期格式为 YYYY-MM-DD"""
        if isinstance(date_str, int):
            return str(date_str)
        
        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]:
            try:
                dt = datetime.strptime(str(date_str), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        raise ValueError(f"Invalid date format: {date_str}")
    
    def _normalize(self, data: pd.DataFrame) -> pd.DataFrame:
        """标准化 DataFrame 格式"""
        # Stooq 返回列名: Open, High, Low, Close, Volume
        # 日期在索引中 (name='Date')
        
        df = data.copy()
        
        # 标准化列名
        df.columns = [c.lower() for c in df.columns]
        
        # 只保留需要的列
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        df = df[required]
        
        # 转换数值
        for col in required:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # 重置索引，把日期变成列
        df = df.reset_index()
        date_col = df.columns[0]
        if str(date_col) != "date":
            df = df.rename(columns={date_col: "date"})
        
        # 转换日期
        df["date"] = pd.to_datetime(df["date"])
        
        # 设置索引并排序
        df = df.set_index("date").sort_index()
        
        return df
    
    def _validate(self, df: pd.DataFrame):
        """验证数据完整性"""
        null_count = df[["open", "high", "low", "close", "volume"]].isnull().sum().sum()
        
        if null_count > 0:
            logger.warning(f"⚠️ [{self.name}] Data contains {null_count} null values")
