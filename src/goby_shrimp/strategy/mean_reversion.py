"""
Mean Reversion Strategy - 均值回归策略

基于 Z-Score 的均值回归策略：
- z < -2.0 → 买入（超跌）
- z > +2.0 → 卖出/做空（超涨）
- |z| < 0.5 → 平仓（回归均值）
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd
import numpy as np

logger = logging.getLogger("goby_shrimp.mean_reversion")


@dataclass
class MeanReversionStrategy:
    """
    均值回归策略
    
    基于 Z-Score 的超买超卖策略
    
    用法:
        strategy = MeanReversionStrategy(
            z_window=20,        # Z-Score 计算窗口
            entry_threshold=2.0,  # 入场阈值
            exit_threshold=0.5,   # 出场阈值
            use_short=True,      # 是否做空
        )
    """
    
    z_window: int = 20           # Z-Score 窗口
    entry_threshold: float = 2.0  # 入场阈值 (std)
    exit_threshold: float = 0.5   # 出场阈值 (std)
    use_short: bool = True        # 是否做空
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        生成交易信号
        
        Args:
            data: OHLCV 数据
            
        Returns:
            pd.Series: 1=做多, -1=做空, 0=空仓
        """
        close = data['close']
        
        # 计算 Z-Score
        rolling_mean = close.rolling(window=self.z_window).mean()
        rolling_std = close.rolling(window=self.z_window).std()
        
        # 避免除零
        rolling_std = rolling_std.replace(0, np.nan)
        
        z_score = (close - rolling_mean) / rolling_std
        
        # 生成信号
        signals = pd.Series(0, index=data.index)
        
        # 超跌 → 做多
        signals[z_score < -self.entry_threshold] = 1
        
        # 超涨 → 做空
        if self.use_short:
            signals[z_score > self.entry_threshold] = -1
        
        # 回归均值 → 平仓
        signals[(z_score > -self.exit_threshold) & (z_score < self.exit_threshold)] = 0
        
        return signals
    
    def get_params(self) -> dict[str, Any]:
        return {
            "name": "MeanReversion",
            "z_window": self.z_window,
            "entry_threshold": self.entry_threshold,
            "exit_threshold": self.exit_threshold,
            "use_short": self.use_short,
        }
    
    def calculate_z_score(self, data: pd.DataFrame) -> pd.Series:
        """计算 Z-Score 序列"""
        close = data['close']
        
        rolling_mean = close.rolling(window=self.z_window).mean()
        rolling_std = close.rolling(window=self.z_window).std()
        
        rolling_std = rolling_std.replace(0, np.nan)
        
        z_score = (close - rolling_mean) / rolling_std
        
        return z_score
    
    def count_crossovers(self, data: pd.DataFrame) -> int:
        """
        统计信号切换次数（用于计算 turnover）
        均值回归策略用信号变化次数
        """
        signals = self.generate_signals(data)
        
        # 信号变化次数
        changes = signals.diff().fillna(0).abs()
        # 1 = -1到0, 0到1, 1到0, 0到-1 等变化
        # -1到1 或 1到-1 是2
        crossover_count = (changes > 0).sum()
        
        return int(crossover_count)


def create_mean_reversion_strategy(
    z_window: int = 20,
    entry_threshold: float = 2.0,
    exit_threshold: float = 0.5,
    use_short: bool = True,
) -> MeanReversionStrategy:
    """创建均值回归策略"""
    return MeanReversionStrategy(
        z_window=z_window,
        entry_threshold=entry_threshold,
        exit_threshold=exit_threshold,
        use_short=use_short,
    )
