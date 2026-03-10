"""
BaseStrategy 抽象基类

所有策略必须继承此类并实现接口
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd

from .signals import Signal


class BaseStrategy(ABC):
    """策略抽象基类"""
    
    name: str = "base"
    
    def __init__(self):
        self._position: int = 0  # 当前持仓: 1=多头, 0=空仓, -1=空头
    
    @property
    def position(self) -> int:
        """当前持仓状态"""
        return self._position
    
    @abstractmethod
    def on_bar(self, bar: pd.Series) -> None:
        """
        每根 K 线触发
        
        Args:
            bar: OHLCV 数据 (pd.Series)
        """
        pass
    
    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> Signal:
        """
        生成交易信号
        
        Args:
            data: 历史 OHLCV 数据，包含 close 列
            
        Returns:
            Signal: BUY / SELL / HOLD
        """
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """重置策略状态"""
        pass

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        向量化信号接口（默认由流式接口迭代适配）

        Returns:
            pd.Series: 1=BUY, -1=SELL, 0=HOLD
        """
        signals = []
        self.reset()
        for idx in range(len(data)):
            signal = self.generate_signal(data.iloc[: idx + 1])
            if signal == Signal.BUY:
                signals.append(1)
            elif signal == Signal.SELL:
                signals.append(-1)
            else:
                signals.append(0)
        return pd.Series(signals, index=data.index)
    
    def __repr__(self):
        return f"{self.__class__.__name__}()"
