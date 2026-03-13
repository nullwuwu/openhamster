"""
RSI 策略

RSI < 30 超卖 → BUY
RSI > 70 超买 → SELL
RSI 从下往上穿越 50 → BUY
RSI 从上往下穿越 50 → SELL
"""
from __future__ import annotations
from typing import Optional
import pandas as pd

from .base_strategy import BaseStrategy
from .signals import Signal


class RSIStrategy(BaseStrategy):
    """RSI 策略"""
    
    name = "rsi"
    
    def __init__(
        self,
        period: int = 14,
        oversold: int = 30,
        overbought: int = 70,
        use_mid_crossover: bool = True,
    ):
        """
        初始化
        
        Args:
            period: RSI 周期 (默认 14)
            oversold: 超卖阈值 (默认 30)
            overbought: 超买阈值 (默认 70)
            use_mid_crossover: 是否使用中线交叉 (50)
        """
        super().__init__()
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.use_mid_crossover = use_mid_crossover
        
        self._rsi: Optional[pd.Series] = None
        self._last_signal: Signal = Signal.HOLD
    
    def reset(self) -> None:
        """重置策略状态"""
        self._rsi = None
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
        if len(data) < self.period + 1:
            return Signal.HOLD
        
        # 计算 RSI
        close = data['close']
        delta = close.diff()
        
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=self.period).mean()
        avg_loss = loss.rolling(window=self.period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        self._rsi = rsi
        
        # 获取当前和前一根 RSI
        current_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]
        
        if pd.isna(current_rsi) or pd.isna(prev_rsi):
            return Signal.HOLD
        
        # 策略1: 超卖反弹 (RSI 从 <30 回到 >30)
        if prev_rsi < self.oversold and current_rsi > self.oversold:
            self._last_signal = Signal.BUY
            return Signal.BUY
        
        # 策略2: 超买回落 (RSI 从 >70 回到 <70)
        if prev_rsi > self.overbought and current_rsi < self.overbought:
            self._last_signal = Signal.SELL
            return Signal.SELL
        
        # 策略3: 中线交叉 (可选)
        if self.use_mid_crossover:
            # RSI 从下往上穿越 50 → BUY
            if prev_rsi < 50 and current_rsi > 50:
                self._last_signal = Signal.BUY
                return Signal.BUY
            
            # RSI 从上往下穿越 50 → SELL
            if prev_rsi > 50 and current_rsi < 50:
                self._last_signal = Signal.SELL
                return Signal.SELL
        
        return Signal.HOLD
    
    def get_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        获取策略指标
        
        Returns:
            DataFrame with RSI
        """
        close = data['close']
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=self.period).mean()
        avg_loss = loss.rolling(window=self.period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return pd.DataFrame({
            'close': close,
            'rsi': rsi,
        })
