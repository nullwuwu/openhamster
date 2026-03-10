"""
策略模块

提供各种交易策略
"""
from .base_strategy import BaseStrategy
from .signals import Signal, BUY, SELL, HOLD
from .ma_cross_strategy import MACrossStrategy
from .rsi_strategy import RSIStrategy
from .macd_strategy import MACDStrategy
from .mean_reversion import MeanReversionStrategy
from .channel_breakout import ChannelBreakoutStrategy
from .factory import (
    LLMStrategySpec,
    StrategyAdapter,
    StrategyFactory,
    StrategyRegistry,
    get_strategy_factory,
    get_strategy_registry,
)

__all__ = [
    "BaseStrategy",
    "Signal",
    "BUY",
    "SELL", 
    "HOLD",
    "MACrossStrategy",
    "RSIStrategy",
    "MACDStrategy",
    "MeanReversionStrategy",
    "ChannelBreakoutStrategy",
    "LLMStrategySpec",
    "StrategyAdapter",
    "StrategyFactory",
    "StrategyRegistry",
    "get_strategy_factory",
    "get_strategy_registry",
]
