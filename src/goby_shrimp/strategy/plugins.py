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
    supported_markets: tuple[str, ...] = ("HK", "CN")
    market_bias: str = "balanced"
    knowledge_families: tuple[str, ...] = ()
    strategy_family_label_zh: str = ""
    knowledge_notes_zh: str = ""


def iter_builtin_strategy_plugins() -> list[StrategyPlugin]:
    return [
        StrategyPlugin(
            name="ma_cross",
            description="Trend-following moving-average crossover baseline.",
            stream_cls=MACrossStrategy,
            default_params={"short_window": 5, "long_window": 20},
            tags=("trend", "moving-average"),
            supported_markets=("HK", "CN"),
            market_bias="hk_preferred",
            knowledge_families=("trend_following",),
            strategy_family_label_zh="趋势跟随",
            knowledge_notes_zh="通过中短期均线关系确认趋势延续，适合作为港股主线趋势基线。",
        ),
        StrategyPlugin(
            name="rsi",
            description="Momentum reversal baseline based on RSI bands.",
            stream_cls=RSIStrategy,
            default_params={"period": 14, "oversold": 30, "overbought": 70},
            tags=("momentum", "oscillator"),
            supported_markets=("CN", "HK"),
            market_bias="cn_preferred",
            knowledge_families=("mean_reversion", "momentum_filter"),
            strategy_family_label_zh="均值回归 / 动量过滤",
            knowledge_notes_zh="利用超买超卖做反转判断，但必须警惕强趋势环境中的持续钝化。",
        ),
        StrategyPlugin(
            name="macd",
            description="Momentum crossover baseline based on MACD signal changes.",
            stream_cls=MACDStrategy,
            default_params={"fast_period": 12, "slow_period": 26, "signal_period": 9},
            tags=("momentum", "trend"),
            supported_markets=("HK", "CN"),
            market_bias="balanced",
            knowledge_families=("trend_following", "momentum_filter"),
            strategy_family_label_zh="趋势跟随 / 动量过滤",
            knowledge_notes_zh="用动量和趋势共振过滤弱信号，避免在无方向区间里高频切换。",
        ),
        StrategyPlugin(
            name="mean_reversion",
            description="Vectorized mean-reversion baseline using z-score envelopes.",
            vectorized_cls=MeanReversionStrategy,
            default_params={"z_window": 20, "entry_threshold": 2.0, "exit_threshold": 0.5, "use_short": False},
            tags=("reversion", "vectorized"),
            supported_markets=("CN", "HK"),
            market_bias="cn_preferred",
            knowledge_families=("mean_reversion",),
            strategy_family_label_zh="均值回归",
            knowledge_notes_zh="依赖偏离回归和波动收敛，不适合趋势快速扩张时直接逆势参与。",
        ),
        StrategyPlugin(
            name="channel_breakout",
            description="Vectorized breakout baseline using price channels and ATR filters.",
            vectorized_cls=ChannelBreakoutStrategy,
            default_params={"channel_window": 20, "atr_window": 14, "atr_k": 2.0},
            tags=("breakout", "vectorized"),
            supported_markets=("HK", "CN"),
            market_bias="hk_preferred",
            knowledge_families=("breakout", "volatility_filter"),
            strategy_family_label_zh="突破 / 波动率过滤",
            knowledge_notes_zh="在波动扩张与区间突破配合时更有效，适合港股指数主导型市场。",
        ),
    ]


def strategy_plugin_names(include_llm_anchor: bool = False) -> list[str]:
    names = [plugin.name for plugin in iter_builtin_strategy_plugins()]
    if include_llm_anchor:
        names.append("novel_composite")
    return names
