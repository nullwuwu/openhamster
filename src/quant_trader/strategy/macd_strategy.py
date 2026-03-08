"""
MACD 策略

MACD 信号线金叉 → BUY
MACD 信号线死叉 → SELL
零轴交叉作为辅助确认
"""
from __future__ import annotations
from typing import Optional
import pandas as pd

from .base_strategy import BaseStrategy
from .signals import Signal


class MACDStrategy(BaseStrategy):
    """MACD 策略"""
    
    name = "macd"
    
    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        use_zero_cross: bool = True,
    ):
        """
        初始化
        
        Args:
            fast_period: 快线周期 (默认 12)
            slow_period: 慢线周期 (默认 26)
            signal_period: 信号线周期 (默认 9)
            use_zero_cross: 是否使用零轴交叉辅助
        """
        super().__init__()
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.use_zero_cross = use_zero_cross
        
        self._macd: Optional[pd.Series] = None
        self._signal: Optional[pd.Series] = None
        self._histogram: Optional[pd.Series] = None
        self._last_signal: Signal = Signal.HOLD
    
    def reset(self) -> None:
        """重置策略状态"""
        self._macd = None
        self._signal = None
        self._histogram = None
        self._last_signal = Signal.HOLD
        self._position = 0
    
    def on_bar(self, bar: pd.Series) -> None:
        """每根 K 线触发"""
        pass
    
    def generate_signal(self, data: pd.DataFrame) -> Signal:
        """
        生成交易信号
        
        Args:
            data: OHLCV 数据，index 为日期
            
        Returns:
            Signal: BUY / SELL / HOLD
        """
        min_period = self.slow_period + self.signal_period
        if len(data) < min_period + 1:
            return Signal.HOLD
        
        # 计算 MACD
        close = data['close']
        
        # EMA
        ema_fast = close.ewm(span=self.fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow_period, adjust=False).mean()
        
        # MACD 线
        macd = ema_fast - ema_slow
        
        # 信号线
        signal = macd.ewm(span=self.signal_period, adjust=False).mean()
        
        # Histogram
        histogram = macd - signal
        
        self._macd = macd
        self._signal = signal
        self._histogram = histogram
        
        # 获取当前和前一根
        current_macd = macd.iloc[-1]
        current_signal = signal.iloc[-1]
        prev_macd = macd.iloc[-2]
        prev_signal = signal.iloc[-2]
        
        if any(pd.isna(x) for x in [current_macd, current_signal, prev_macd, prev_signal]):
            return Signal.HOLD
        
        # 策略1: MACD 金叉 (MACD 从下往上穿越信号线)
        if prev_macd <= prev_signal and current_macd > current_signal:
            self._last_signal = Signal.BUY
            return Signal.BUY
        
        # 策略2: MACD 死叉 (MACD 从上往下穿越信号线)
        if prev_macd >= prev_signal and current_macd < current_signal:
            self._last_signal = Signal.SELL
            return Signal.SELL
        
        # 策略3: 零轴交叉 (辅助)
        if self.use_zero_cross:
            current_histogram = histogram.iloc[-1]
            prev_histogram = histogram.iloc[-2]
            
            # MACD 从负转正 (多头)
            if pd.notna(prev_histogram) and pd.notna(current_histogram):
                if prev_histogram < 0 and current_histogram > 0:
                    # 避免重复信号
                    if self._last_signal != Signal.BUY:
                        self._last_signal = Signal.BUY
                        return Signal.BUY
                
                # MACD 从正转负 (空头)
                if prev_histogram > 0 and current_histogram < 0:
                    if self._last_signal != Signal.SELL:
                        self._last_signal = Signal.SELL
                        return Signal.SELL
        
        return Signal.HOLD
    
    def get_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        获取策略指标
        
        Returns:
            DataFrame with MACD, Signal, Histogram
        """
        close = data['close']
        
        ema_fast = close.ewm(span=self.fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow_period, adjust=False).mean()
        
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=self.signal_period, adjust=False).mean()
        histogram = macd - signal
        
        return pd.DataFrame({
            'close': close,
            'macd': macd,
            'signal': signal,
            'histogram': histogram,
        })
