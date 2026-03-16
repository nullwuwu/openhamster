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
from .plugins import StrategyPlugin, iter_builtin_strategy_plugins, strategy_plugin_names
from .knowledge import (
    StrategyKnowledge,
    get_strategy_knowledge,
    get_strategy_knowledge_catalog,
    knowledge_payload_for_market,
    knowledge_preferences_from_market_profile,
)
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
    "StrategyPlugin",
    "StrategyKnowledge",
    "LLMStrategySpec",
    "StrategyAdapter",
    "StrategyFactory",
    "StrategyRegistry",
    "iter_builtin_strategy_plugins",
    "strategy_plugin_names",
    "get_strategy_knowledge",
    "get_strategy_knowledge_catalog",
    "knowledge_payload_for_market",
    "knowledge_preferences_from_market_profile",
    "get_strategy_factory",
    "get_strategy_registry",
]
