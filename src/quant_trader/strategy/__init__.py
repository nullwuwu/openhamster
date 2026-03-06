"""
策略模块

提供各种交易策略
"""
from .base_strategy import BaseStrategy
from .signals import Signal, BUY, SELL, HOLD
from .ma_cross_strategy import MACrossStrategy

__all__ = [
    "BaseStrategy",
    "Signal",
    "BUY",
    "SELL", 
    "HOLD",
    "MACrossStrategy",
]
