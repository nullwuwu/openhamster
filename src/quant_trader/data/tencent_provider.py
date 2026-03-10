"""
腾讯财经数据源

提供港股历史 K 线数据
"""
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

from .base import DataProvider

logger = logging.getLogger("quant_trader.data.tencent")


class TencentProvider(DataProvider):
    """
    腾讯财经数据源
    
    支持港股历史 K 线
    """
    
    name = "tencent"
    
    # 港股代码映射: 0700.HK -> hk00700
    TENCENT_CODE_MAP = {
        "0700.HK": "hk00700",
        "2800.HK": "hk02800",
        "9988.HK": "hk09988",
    }
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.session = requests.Session()
    
    def _convert_code(self, ticker: str) -> str:
        """转换股票代码为腾讯格式"""
        if ticker in self.TENCENT_CODE_MAP:
            return self.TENCENT_CODE_MAP[ticker]
        
        # 尝试自动转换: 0700.HK -> hk00700
        if ".HK" in ticker:
            code = ticker.replace(".HK", "")
            return f"hk{code.zfill(5)}"
        
        return ticker
    
    def fetch_ohlcv(
        self,
        ticker: str,
        start: str,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        获取 OHLCV 数据
        
        Args:
            ticker: 股票代码，如 "0700.HK"
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            
        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        tencent_code = self._convert_code(ticker)
        
        # 计算天数
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d") if end else datetime.now()
        days = max((end_dt - start_dt).days + 30, 320)  # 至少 320 天
        
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {
            "param": f"{tencent_code},day,,,{days},qfq"  # qfq = 前复权
        }
        
        last_error = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"📥 [tencent] Fetching {ticker} from {start} to {end}")
                
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                
                # 解析数据
                stock_data = data.get("data", {}).get(tencent_code, {})
                day_data = stock_data.get("day", [])
                
                if not day_data:
                    raise ValueError(f"No data for {ticker}")
                
                # 转换为 DataFrame
                records = []
                for item in day_data:
                    date = item[0]
                    open_price = float(item[1])
                    close = float(item[2])
                    high = float(item[3])
                    low = float(item[4])
                    volume = float(item[5])
                    
                    records.append(
                        {
                            "date": date,
                            "open": open_price,
                            "high": high,
                            "low": low,
                            "close": close,
                            "volume": volume,
                        }
                    )
                
                df = pd.DataFrame(records)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                
                # 过滤日期范围
                start_dt = pd.to_datetime(start)
                end_dt = pd.to_datetime(end) if end else datetime.now()
                df = df[(df.index >= start_dt) & (df.index <= end_dt)]
                
                logger.info(f"✅ [tencent] Loaded {len(df)} rows for {ticker}")
                return df
                
            except Exception as e:
                logger.warning(f"⚠️ [tencent] Attempt {attempt} failed: {e}")
                last_error = e
                if attempt < self.max_retries:
                    import time
                    time.sleep(1.0 * attempt)
        
        raise RuntimeError(f"{self.name} failed after {self.max_retries} attempts: {last_error}")
