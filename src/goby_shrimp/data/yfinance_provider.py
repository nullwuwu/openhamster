"""
YFinance 数据源

基于 Yahoo Finance 直接 API 的数据提供者
绕过 yfinance Python 包的限流问题
"""
from __future__ import annotations
import logging
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

from .base import DataProvider

logger = logging.getLogger("goby_shrimp.data.yfinance")

# Yahoo Finance API 端点
YAHOO_FINANCE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

# 请求头，模拟浏览器
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


class YFinanceProvider(DataProvider):
    """Yahoo Finance API 数据源"""
    
    name = "yfinance"
    
    def __init__(self, max_retries: int = 3, rate_limit_wait: float = 1.0):
        """
        初始化
        
        Args:
            max_retries: 最大重试次数
            rate_limit_wait: 请求间隔（秒），避免触发限流
        """
        self.max_retries = max_retries
        self.rate_limit_wait = rate_limit_wait
    
    def fetch_ohlcv(
        self, 
        ticker: str, 
        start: str, 
        end: Optional[str] = None
    ) -> pd.DataFrame:
        """从 Yahoo Finance API 获取数据"""
        logger.info(f"📥 [{self.name}] Fetching {ticker} from {start} to {end}")
        
        # 转换日期为时间戳
        start_ts = self._date_to_timestamp(start)
        end_ts = self._date_to_timestamp(end) if end else int(datetime.now().timestamp())
        
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # 速率限制
                if attempt > 0:
                    wait_time = self.rate_limit_wait * (2 ** attempt)  # 指数退避
                    logger.info(f"⏳ [{self.name}] Waiting {wait_time:.1f}s before retry...")
                    time.sleep(wait_time)
                
                data = self._fetch_from_api(ticker, start_ts, end_ts)
                
                if data is None or data.empty:
                    last_error = f"No data for {ticker}"
                    logger.warning(f"⚠️ [{self.name}] Attempt {attempt + 1}: {last_error}")
                    continue
                
                logger.info(f"✅ [{self.name}] Loaded {len(data)} rows for {ticker}")
                return data
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"⚠️ [{self.name}] Attempt {attempt + 1} failed: {e}")
        
        raise RuntimeError(f"{self.name} failed after {self.max_retries} attempts: {last_error}")
    
    def _fetch_from_api(
        self, 
        ticker: str, 
        period1: int, 
        period2: int
    ) -> Optional[pd.DataFrame]:
        """从 Yahoo Finance API 获取数据"""
        url = YAHOO_FINANCE_URL.format(ticker=ticker)
        params = {
            "period1": period1,
            "period2": period2,
            "interval": "1d",
        }
        
        resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()
        
        data = resp.json()
        
        # 检查 API 响应
        if "chart" not in data:
            raise RuntimeError(f"Invalid API response: {data}")
        
        result = data["chart"].get("result")
        if not result or result[0] is None:
            # 检查错误信息
            error = data.get("chart", {}).get("error")
            if error:
                raise RuntimeError(f"API error: {error.get('description', error)}")
            return None
        
        result = result[0]
        
        # 提取数据
        timestamps = result.get("timestamp", [])
        if not timestamps:
            return None
        
        quotes = result.get("indicators", {}).get("quote", [{}])[0]
        
        # 构建 DataFrame
        df = pd.DataFrame({
            "datetime": pd.to_datetime(timestamps, unit="s"),
            "open": quotes.get("open"),
            "high": quotes.get("high"),
            "low": quotes.get("low"),
            "close": quotes.get("close"),
            "volume": quotes.get("volume"),
        })
        
        # 过滤无效行 (OHLCV 全为 NaN)
        df = df.dropna(subset=["close"])
        
        # 设置索引
        df = df.set_index("datetime")
        df = df.sort_index()
        
        # 标准化列名
        df.columns = [c.lower() for c in df.columns]
        
        return df
    
    def _date_to_timestamp(self, date_str: str) -> int:
        """将日期字符串转换为时间戳"""
        if isinstance(date_str, int):
            return date_str
        
        # 解析日期
        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]:
            try:
                dt = datetime.strptime(str(date_str), fmt)
                return int(dt.timestamp())
            except ValueError:
                continue
        
        raise ValueError(f"Invalid date format: {date_str}")
