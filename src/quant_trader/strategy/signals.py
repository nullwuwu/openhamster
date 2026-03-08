"""
信号定义

定义交易信号枚举
"""
from enum import Enum


class Signal(Enum):
    """交易信号"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"Signal.{self.name}"


# 别名
BUY = Signal.BUY
SELL = Signal.SELL
HOLD = Signal.HOLD
