"""
Channel Breakout Strategy - Donchian Channel 通道突破策略

基于 Donchian Channel 的突破策略：
- 收盘价突破 N 日高点 → 买入
- 收盘价跌破 N 日低点 → 平仓
- ATR 动态止损
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd
import numpy as np

logger = logging.getLogger("openhamster.channel_breakout")


@dataclass
class ChannelBreakoutStrategy:
    """
    Donchian Channel 突破策略
    
    用法:
        strategy = ChannelBreakoutStrategy(
            channel_window=20,   # 通道窗口
            atr_window=14,       # ATR 窗口
            atr_k=2.0,          # ATR 止损倍数
        )
    """
    
    channel_window: int = 20    # 通道窗口 (N日)
    atr_window: int = 14        # ATR 窗口
    atr_k: float = 2.0          # ATR 止损倍数
    use_stop_loss: bool = True   # 是否使用 ATR 止损
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        生成交易信号
        
        Args:
            data: OHLCV 数据
            
        Returns:
            pd.Series: 1=做多, 0=空仓
        """
        close = data['close']
        high = data['high']
        low = data['low']
        
        # Donchian Channel
        upper_channel = high.rolling(window=self.channel_window).max()
        lower_channel = low.rolling(window=self.channel_window).min()
        
        # ATR (Average True Range)
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.atr_window).mean()
        
        # 信号
        signals = pd.Series(0, index=data.index)
        
        # 突破上轨 → 买入
        breakout = close > upper_channel.shift(1)
        signals[breakout] = 1
        
        # 跌破下轨 → 平仓
        breakdown = close < lower_channel.shift(1)
        signals[breakdown] = 0
        
        # ATR 止损 (可选)
        if self.use_stop_loss:
            # 计算持仓期间的最高价
            entry_price = close.copy()
            in_position = False
            
            for i in range(self.channel_window, len(signals)):
                if signals.iloc[i] == 1 and not in_position:
                    # 开多仓
                    entry_price.iloc[i] = close.iloc[i]
                    in_position = True
                elif in_position and signals.iloc[i] == 0:
                    # 平仓
                    in_position = False
                elif in_position:
                    # 检查 ATR 止损
                    stop_price = entry_price.iloc[i] - self.atr_k * atr.iloc[i]
                    if close.iloc[i] < stop_price:
                        signals.iloc[i] = 0  # 止损平仓
                        in_position = False
        
        return signals
    
    def get_params(self) -> dict[str, Any]:
        return {
            "name": "ChannelBreakout",
            "channel_window": self.channel_window,
            "atr_window": self.atr_window,
            "atr_k": self.atr_k,
            "use_stop_loss": self.use_stop_loss,
        }
    
    def count_crossovers(self, data: pd.DataFrame) -> int:
        """统计信号切换次数"""
        signals = self.generate_signals(data)
        changes = signals.diff().fillna(0).abs()
        return int((changes > 0).sum())


def create_channel_breakout_strategy(
    channel_window: int = 20,
    atr_window: int = 14,
    atr_k: float = 2.0,
    use_stop_loss: bool = True,
) -> ChannelBreakoutStrategy:
    """创建通道突破策略"""
    return ChannelBreakoutStrategy(
        channel_window=channel_window,
        atr_window=atr_window,
        atr_k=atr_k,
        use_stop_loss=use_stop_loss,
    )
