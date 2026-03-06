"""
信号定义

定义交易信号枚举
"""
from enum import Enum


class Signal(Enum):
    """交易信号"""
    BUY = 1
    SELL = -1
    HOLD = 0
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"Signal.{self.name}"


# 别名
BUY = Signal.BUY
SELL = Signal.SELL
HOLD = Signal.HOLD
