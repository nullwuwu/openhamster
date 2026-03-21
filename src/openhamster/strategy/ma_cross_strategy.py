"""
双均线交叉策略

MA5 上穿 MA20 → BUY
MA5 下穿 MA20 → SELL
其余 → HOLD
"""
from __future__ import annotations
import pandas as pd

from .base_strategy import BaseStrategy
from .signals import Signal


class MACrossStrategy(BaseStrategy):
    """双均线交叉策略"""
    
    name = "ma_cross"
    
    def __init__(self, short_window: int = 5, long_window: int = 20):
        """
        初始化
        
        Args:
            short_window: 短期均线周期
            long_window: 长期均线周期
        """
        super().__init__()
        self.short_window = short_window
        self.long_window = long_window
        
        self._short_ma: Optional[pd.Series] = None
        self._long_ma: Optional[pd.Series] = None
        self._last_signal: Signal = Signal.HOLD
    
    def reset(self) -> None:
        """重置策略状态"""
        self._short_ma = None
        self._long_ma = None
        self._last_signal = Signal.HOLD
        self._position = 0
    
    def on_bar(self, bar: pd.Series) -> None:
        """
        每根 K 线触发（可选实现，用于实时计算）
        
        Args:
            bar: OHLCV 数据
        """
        # 实时策略可以在此更新状态
        pass
    
    def generate_signal(self, data: pd.DataFrame) -> Signal:
        """
        生成交易信号
        
        Args:
            data: OHLCV 数据，index 为日期
            
        Returns:
            Signal: BUY / SELL / HOLD
        """
        if len(data) < self.long_window:
            return Signal.HOLD
        
        # 兼容大小写列名
        close_col = 'Close' if 'Close' in data.columns else 'close'
        close = data[close_col]
        
        # 短期均线
        short_ma = close.rolling(window=self.short_window).mean()
        # 长期均线
        long_ma = close.rolling(window=self.long_window).mean()
        
        # 获取最新值
        current_short = short_ma.iloc[-1]
        current_long = long_ma.iloc[-1]
        
        # 前一根的值
        prev_short = short_ma.iloc[-2]
        prev_long = long_ma.iloc[-2]
        
        # 判断交叉
        if pd.isna(current_short) or pd.isna(current_long):
            return Signal.HOLD
        
        if pd.isna(prev_short) or pd.isna(prev_long):
            return Signal.HOLD
        
        # 金叉：短期均线上穿长期均线 → 买入
        if prev_short <= prev_long and current_short > current_long:
            self._last_signal = Signal.BUY
            return Signal.BUY
        
        # 死叉：短期均线下穿长期均线 → 卖出
        elif prev_short >= prev_long and current_short < current_long:
            self._last_signal = Signal.SELL
            return Signal.SELL
        
        else:
            return Signal.HOLD
    
    def get_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        获取策略指标（用于可视化）
        
        Returns:
            DataFrame with MA columns
        """
        # 兼容大小写列名
        close_col = 'Close' if 'Close' in data.columns else 'close'
        close = data[close_col]
        return pd.DataFrame({
            'close': close,
            'ma_short': close.rolling(window=self.short_window).mean(),
            'ma_long': close.rolling(window=self.long_window).mean(),
        })
