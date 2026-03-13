"""
iTick 数据源

提供港股、美股、期货等数据
"""
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

from .base import DataProvider
from ..config import get_settings

logger = logging.getLogger("goby_shrimp.data.itick")

# iTick API 配置
ITICK_BASE_URL = "https://api.itick.org"


class ITickProvider(DataProvider):
    """
    iTick 数据源
    
    支持: 港股、美股、期货、外汇、加密货币
    免费版: 5次/分钟
    """
    
    name = "itick"
    
    # 市场代码映射
    REGION_MAP = {
        "2800.HK": ("stock", "HK"),
        "0700.HK": ("stock", "HK"),
        "9988.HK": ("stock", "HK"),
        "AAPL": ("stock", "US"),
        "MSFT": ("stock", "US"),
        "GOOGL": ("stock", "US"),
        "AMZN": ("stock", "US"),
        "TSLA": ("stock", "US"),
        "NVDA": ("stock", "US"),
        "META": ("stock", "US"),
        "CL=F": ("future", "US"),
        "GC=F": ("future", "US"),
        "SI=F": ("future", "US"),
    }
    
    # K线间隔映射 (itick: 日K=6, 60分钟=5, 30分钟=4, 15分钟=3, 5分钟=2, 1分钟=1)
    INTERVAL_MAP = {
        "1d": 6,
        "1h": 5,
        "30m": 4,
        "15m": 3,
        "5m": 2,
        "1m": 1,
    }
    
    def __init__(self, token: str = None, max_retries: int = 3):
        settings = get_settings()
        self.token = token or settings.integrations.itick_token
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "accept": "application/json",
            "token": self.token,
        })
    
    def _convert_ticker(self, ticker: str) -> tuple:
        """转换股票代码为 itick 格式"""
        if ticker in self.REGION_MAP:
            return self.REGION_MAP[ticker]
        
        # 自动检测
        if ".HK" in ticker:
            return ("stock", "HK")
        elif "=F" in ticker:
            return ("future", "US")
        else:
            return ("stock", "US")
    
    def _convert_code(self, ticker: str) -> str:
        """提取股票代码"""
        return ticker.replace(".HK", "").replace("=F", "")
    
    def fetch_ohlcv(
        self,
        ticker: str,
        start: str,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        获取 OHLCV 数据
        
        Args:
            ticker: 股票代码，如 "0700.HK", "AAPL", "CL=F"
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            
        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        ptype, region = self._convert_ticker(ticker)
        code = self._convert_code(ticker)
        
        # 计算数量 (默认取约 60 天日线)
        days = 60
        if end and start:
            from datetime import datetime
            days = (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days + 10
        
        interval = self.INTERVAL_MAP.get("1d", 6)
        
        url = f"{ITICK_BASE_URL}/kline"
        params = {
            "type": ptype,
            "region": region,
            "code": code,
            "interval": interval,
            "size": min(days, 500),
        }
        
        last_error = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"📥 [itick] Fetching {ticker} from {start}")
                
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("code") != 0:
                    raise ValueError(f"API error: {data.get('msg')}")
                
                klines = data.get("data", [])
                
                if not klines:
                    raise ValueError(f"No data for {ticker}")
                
                # 转换为 DataFrame
                records = []
                for k in klines:
                    records.append(
                        {
                            "date": k.get("t", ""),
                            "open": k.get("o", 0),
                            "high": k.get("h", 0),
                            "low": k.get("l", 0),
                            "close": k.get("c", 0),
                            "volume": k.get("v", 0),
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
                
                logger.info(f"✅ [itick] Loaded {len(df)} rows for {ticker}")
                return df
                
            except Exception as e:
                logger.warning(f"⚠️ [itick] Attempt {attempt} failed: {e}")
                last_error = e
                if attempt < self.max_retries:
                    import time
                    time.sleep(1.0 * attempt)
        
        raise RuntimeError(f"{self.name} failed after {self.max_retries} attempts: {last_error}")
    
    def get_quote(self, ticker: str) -> Optional[dict]:
        """获取实时报价"""
        ptype, region = self._convert_ticker(ticker)
        code = self._convert_code(ticker)
        
        url = f"{ITICK_BASE_URL}/quote"
        params = {
            "type": ptype,
            "region": region,
            "code": code,
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get("code") == 0:
                return data.get("data", [{}])[0]
        except Exception as e:
            logger.warning(f"⚠️ [itick] Quote failed: {e}")
        
        return None
