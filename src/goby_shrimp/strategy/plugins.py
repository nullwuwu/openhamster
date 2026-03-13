from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .channel_breakout import ChannelBreakoutStrategy
from .ma_cross_strategy import MACrossStrategy
from .macd_strategy import MACDStrategy
from .mean_reversion import MeanReversionStrategy
from .rsi_strategy import RSIStrategy


@dataclass(frozen=True)
class StrategyPlugin:
    name: str
    description: str
    stream_cls: type | None = None
    vectorized_cls: type | None = None
    default_params: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()


def iter_builtin_strategy_plugins() -> list[StrategyPlugin]:
    return [
        StrategyPlugin(
            name="ma_cross",
            description="Trend-following moving-average crossover baseline.",
            stream_cls=MACrossStrategy,
            default_params={"short_window": 5, "long_window": 20},
            tags=("trend", "moving-average"),
        ),
        StrategyPlugin(
            name="rsi",
            description="Momentum reversal baseline based on RSI bands.",
            stream_cls=RSIStrategy,
            default_params={"period": 14, "oversold": 30, "overbought": 70},
            tags=("momentum", "oscillator"),
        ),
        StrategyPlugin(
            name="macd",
            description="Momentum crossover baseline based on MACD signal changes.",
            stream_cls=MACDStrategy,
            default_params={"fast_period": 12, "slow_period": 26, "signal_period": 9},
            tags=("momentum", "trend"),
        ),
        StrategyPlugin(
            name="mean_reversion",
            description="Vectorized mean-reversion baseline using z-score envelopes.",
            vectorized_cls=MeanReversionStrategy,
            default_params={"z_window": 20, "entry_threshold": 2.0, "exit_threshold": 0.5, "use_short": False},
            tags=("reversion", "vectorized"),
        ),
        StrategyPlugin(
            name="channel_breakout",
            description="Vectorized breakout baseline using price channels and ATR filters.",
            vectorized_cls=ChannelBreakoutStrategy,
            default_params={"channel_window": 20, "atr_window": 14, "atr_k": 2.0},
            tags=("breakout", "vectorized"),
        ),
    ]


def strategy_plugin_names(include_llm_anchor: bool = False) -> list[str]:
    names = [plugin.name for plugin in iter_builtin_strategy_plugins()]
    if include_llm_anchor:
        names.append("novel_composite")
    return names
