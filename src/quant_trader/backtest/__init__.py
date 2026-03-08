"""
回测模块

提供回测引擎和结果
"""
from .backtester import Backtester
from .result import BacktestResult
from .optimizer import GridSearchOptimizer, MultiStrategyOptimizer, STRATEGY_PARAMS
from .walk_forward import WalkForwardEngine, WalkForwardResult

__all__ = [
    "Backtester",
    "BacktestResult",
    "GridSearchOptimizer",
    "MultiStrategyOptimizer",
    "STRATEGY_PARAMS",
    "WalkForwardEngine",
    "WalkForwardResult",
]
