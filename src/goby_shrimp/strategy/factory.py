"""
策略注册表与工厂
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .base_strategy import BaseStrategy
from .plugins import StrategyPlugin, iter_builtin_strategy_plugins
from .signals import Signal


@dataclass
class LLMStrategySpec:
    """
    预留：LLM 产出策略规范（阶段2）
    """

    name: str
    mode: str = "stream"
    params: dict[str, Any] = field(default_factory=dict)
    prompt: str = ""


class StrategyAdapter(BaseStrategy):
    """
    将流式策略/向量策略统一为双模式接口
    """

    def __init__(self, strategy: Any, name: str):
        super().__init__()
        self.strategy = strategy
        self.name = name

    def on_bar(self, bar: pd.Series) -> None:
        if hasattr(self.strategy, "on_bar"):
            self.strategy.on_bar(bar)

    def reset(self) -> None:
        if hasattr(self.strategy, "reset"):
            self.strategy.reset()
        self._position = 0

    def generate_signal(self, data: pd.DataFrame) -> Signal:
        if hasattr(self.strategy, "generate_signal"):
            signal = self.strategy.generate_signal(data)
            if isinstance(signal, Signal):
                return signal
            if str(signal).upper() == "BUY":
                return Signal.BUY
            if str(signal).upper() == "SELL":
                return Signal.SELL
            return Signal.HOLD

        if hasattr(self.strategy, "generate_signals"):
            series = self.strategy.generate_signals(data)
            if series is None or len(series) == 0:
                return Signal.HOLD
            value = float(series.iloc[-1])
            if value > 0:
                return Signal.BUY
            if value < 0:
                return Signal.SELL
            return Signal.HOLD

        return Signal.HOLD

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        if hasattr(self.strategy, "generate_signals"):
            series = self.strategy.generate_signals(data)
            if isinstance(series, pd.Series):
                return series
        return super().generate_signals(data)

    def count_crossovers(self, data: pd.DataFrame) -> int:
        if hasattr(self.strategy, "count_crossovers"):
            return int(self.strategy.count_crossovers(data))
        signals = self.generate_signals(data).fillna(0)
        return int((signals.diff().fillna(0).abs() > 0).sum())

    def calculate_param_sensitivity(
        self,
        data: pd.DataFrame,
        perturb_pct: float = 0.10,
    ) -> float:
        if hasattr(self.strategy, "calculate_param_sensitivity"):
            return float(self.strategy.calculate_param_sensitivity(data, perturb_pct=perturb_pct))
        return 0.0

    def get_params(self) -> dict[str, Any]:
        if hasattr(self.strategy, "get_params"):
            return self.strategy.get_params()
        return {"name": self.name}


@dataclass
class StrategyDefinition:
    name: str
    description: str = ""
    stream_cls: type | None = None
    vectorized_cls: type | None = None
    default_params: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    supported_markets: tuple[str, ...] = ("HK", "CN")
    market_bias: str = "balanced"


class StrategyRegistry:
    """策略注册表"""

    def __init__(self):
        self._defs: dict[str, StrategyDefinition] = {}

    def register(
        self,
        name: str,
        description: str = "",
        stream_cls: type | None = None,
        vectorized_cls: type | None = None,
        default_params: dict[str, Any] | None = None,
        tags: tuple[str, ...] | None = None,
        supported_markets: tuple[str, ...] | None = None,
        market_bias: str = "balanced",
    ) -> None:
        key = name.strip().lower()
        self._defs[key] = StrategyDefinition(
            name=key,
            description=description,
            stream_cls=stream_cls,
            vectorized_cls=vectorized_cls,
            default_params=default_params or {},
            tags=tags or (),
            supported_markets=supported_markets or ("HK", "CN"),
            market_bias=market_bias,
        )

    def register_plugin(self, plugin: StrategyPlugin) -> None:
        self.register(
            name=plugin.name,
            description=plugin.description,
            stream_cls=plugin.stream_cls,
            vectorized_cls=plugin.vectorized_cls,
            default_params=dict(plugin.default_params),
            tags=plugin.tags,
            supported_markets=plugin.supported_markets,
            market_bias=plugin.market_bias,
        )

    def get(self, name: str) -> StrategyDefinition:
        key = name.strip().lower()
        if key not in self._defs:
            raise ValueError(f"Unknown strategy: {name}. Available: {list(self._defs)}")
        return self._defs[key]

    def names(self) -> list[str]:
        return sorted(self._defs.keys())

    def definitions(self) -> list[StrategyDefinition]:
        return [self._defs[name] for name in self.names()]


class StrategyFactory:
    """策略工厂"""

    def __init__(self, registry: StrategyRegistry):
        self.registry = registry

    def create(
        self,
        name: str,
        mode: str = "auto",
        params: dict[str, Any] | None = None,
    ) -> StrategyAdapter:
        definition = self.registry.get(name)
        merged_params = {**definition.default_params, **(params or {})}

        chosen_cls: type | None
        if mode == "stream":
            chosen_cls = definition.stream_cls or definition.vectorized_cls
        elif mode == "vectorized":
            chosen_cls = definition.vectorized_cls or definition.stream_cls
        else:
            chosen_cls = definition.stream_cls or definition.vectorized_cls

        if chosen_cls is None:
            raise ValueError(f"Strategy {name} has no implementation")
        instance = chosen_cls(**merged_params)
        return StrategyAdapter(strategy=instance, name=definition.name)


def create_default_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    for plugin in iter_builtin_strategy_plugins():
        registry.register_plugin(plugin)
    return registry


_default_registry: StrategyRegistry | None = None
_default_factory: StrategyFactory | None = None


def get_strategy_registry() -> StrategyRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = create_default_registry()
    return _default_registry


def get_strategy_factory() -> StrategyFactory:
    global _default_factory
    if _default_factory is None:
        _default_factory = StrategyFactory(get_strategy_registry())
    return _default_factory
