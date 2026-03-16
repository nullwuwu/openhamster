from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class StrategyKnowledge:
    knowledge_id: str
    family_key: str
    label_zh: str
    summary_zh: str
    core_logic_zh: str
    supported_markets: tuple[str, ...] = ("HK", "CN")
    preferred_market_conditions: tuple[str, ...] = ()
    discouraged_market_conditions: tuple[str, ...] = ()
    common_indicators: tuple[str, ...] = ()
    common_failure_modes: tuple[str, ...] = ()
    parameter_priors: dict[str, dict[str, Any]] = field(default_factory=dict)
    risk_flags: tuple[str, ...] = ()
    related_baselines: tuple[str, ...] = ()
    novelty_expectation: str = ""
    source_type: str = "builtin"
    source_refs: tuple[str, ...] = ("repo_baseline", "market_profile", "governance_rules")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["supported_markets"] = list(self.supported_markets)
        payload["preferred_market_conditions"] = list(self.preferred_market_conditions)
        payload["discouraged_market_conditions"] = list(self.discouraged_market_conditions)
        payload["common_indicators"] = list(self.common_indicators)
        payload["common_failure_modes"] = list(self.common_failure_modes)
        payload["risk_flags"] = list(self.risk_flags)
        payload["related_baselines"] = list(self.related_baselines)
        payload["source_refs"] = list(self.source_refs)
        return payload


STRATEGY_KNOWLEDGE_CATALOG: dict[str, StrategyKnowledge] = {
    "trend_following": StrategyKnowledge(
        knowledge_id="knowledge_trend_following_v1",
        family_key="trend_following",
        label_zh="趋势跟随",
        summary_zh="顺着已经形成的方向持有，依靠趋势延续获取收益。",
        core_logic_zh="当价格与中期趋势一致并持续强化时进入，避免在趋势未形成时频繁来回切换。",
        supported_markets=("HK", "CN"),
        preferred_market_conditions=("bullish", "trending_up", "persistent_trend"),
        discouraged_market_conditions=("range_bound", "choppy_reversal"),
        common_indicators=("SMA", "EMA", "MACD", "ADX"),
        common_failure_modes=("trend_breakdown", "false_breakout", "sideways_whipsaw"),
        parameter_priors={
            "short_window": {"min": 3, "max": 20},
            "long_window": {"min": 15, "max": 90},
            "fast_period": {"min": 5, "max": 20},
            "slow_period": {"min": 15, "max": 60},
            "signal_period": {"min": 5, "max": 18},
        },
        risk_flags=("slow_signal_lag", "range_market_whipsaw"),
        related_baselines=("ma_cross", "macd"),
        novelty_expectation="合理变体应体现不同的趋势过滤、入场确认或风控节奏；仅微调窗口不算强新策略。",
    ),
    "mean_reversion": StrategyKnowledge(
        knowledge_id="knowledge_mean_reversion_v1",
        family_key="mean_reversion",
        label_zh="均值回归",
        summary_zh="在价格短期偏离过大时，押注其回到中枢。",
        core_logic_zh="利用短期过度扩张后的回落或反弹，通常依赖波动收敛和情绪回归而获利。",
        supported_markets=("HK", "CN"),
        preferred_market_conditions=("range_bound", "volatility_compression"),
        discouraged_market_conditions=("strong_trend", "breakout_expansion"),
        common_indicators=("RSI", "Bollinger", "volatility"),
        common_failure_modes=("trend_dominance", "falling_knife", "late_reversal"),
        parameter_priors={
            "period": {"min": 5, "max": 30},
            "oversold": {"min": 10, "max": 40},
            "overbought": {"min": 60, "max": 90},
            "z_window": {"min": 10, "max": 60},
            "entry_threshold": {"min": 1.0, "max": 3.5},
            "exit_threshold": {"min": 0.1, "max": 1.5},
        },
        risk_flags=("trend_fade_risk", "oversold_can_stay_oversold"),
        related_baselines=("rsi", "mean_reversion"),
        novelty_expectation="合理变体应加入状态过滤、波动约束或退出机制变化；只改 RSI 阈值通常只是轻微变体。",
    ),
    "breakout": StrategyKnowledge(
        knowledge_id="knowledge_breakout_v1",
        family_key="breakout",
        label_zh="突破",
        summary_zh="等待区间被有效打破，再顺着突破方向入场。",
        core_logic_zh="价格在压缩或盘整后出现有效突破时进场，依赖趋势扩张而不是均值回归。",
        supported_markets=("HK", "CN"),
        preferred_market_conditions=("breakout_expansion", "trend_resumption"),
        discouraged_market_conditions=("range_bound", "low_conviction"),
        common_indicators=("Donchian", "ATR", "volatility"),
        common_failure_modes=("false_breakout", "low_volume_breakout", "post_breakout_reversal"),
        parameter_priors={
            "channel_window": {"min": 10, "max": 60},
            "atr_window": {"min": 5, "max": 30},
            "atr_k": {"min": 0.5, "max": 4.0},
        },
        risk_flags=("false_breakout_risk", "gap_reversal"),
        related_baselines=("channel_breakout",),
        novelty_expectation="合理变体应体现突破确认、波动过滤或出场规则差异；只改通道窗口通常不算强新策略。",
    ),
    "momentum_filter": StrategyKnowledge(
        knowledge_id="knowledge_momentum_filter_v1",
        family_key="momentum_filter",
        label_zh="动量过滤",
        summary_zh="用动量方向判断何时放行或阻止主策略入场。",
        core_logic_zh="不单独负责完整交易逻辑，而是作为方向过滤器，减少逆势或弱势环境下的错误信号。",
        supported_markets=("HK", "CN"),
        preferred_market_conditions=("persistent_trend", "leadership_concentration"),
        discouraged_market_conditions=("sharp_reversal", "event_shock"),
        common_indicators=("MACD", "ROC", "RSI"),
        common_failure_modes=("late_confirmation", "momentum_exhaustion"),
        parameter_priors={
            "fast_period": {"min": 5, "max": 20},
            "slow_period": {"min": 15, "max": 60},
            "signal_period": {"min": 4, "max": 18},
        },
        risk_flags=("late_entry", "exhaustion_chase"),
        related_baselines=("macd", "rsi"),
        novelty_expectation="合理变体应体现它如何与主策略协同，而不是单独把动量指标重命名为新策略。",
    ),
    "volatility_filter": StrategyKnowledge(
        knowledge_id="knowledge_volatility_filter_v1",
        family_key="volatility_filter",
        label_zh="波动率过滤",
        summary_zh="通过波动状态筛掉噪音环境，或只在波动扩张/收敛时允许策略触发。",
        core_logic_zh="把波动率当成环境门槛，而不是单独的收益来源，用于提高其他策略的入场质量。",
        supported_markets=("HK", "CN"),
        preferred_market_conditions=("volatility_compression", "orderly_expansion"),
        discouraged_market_conditions=("chaotic_volatility", "event_shock"),
        common_indicators=("ATR", "volatility", "drawdown"),
        common_failure_modes=("volatility_spike", "filter_too_strict", "filter_too_loose"),
        parameter_priors={
            "atr_window": {"min": 5, "max": 30},
            "atr_k": {"min": 0.5, "max": 4.0},
        },
        risk_flags=("filter_overfit", "missed_moves"),
        related_baselines=("channel_breakout",),
        novelty_expectation="合理变体应体现过滤逻辑如何服务主策略；单独换一个 ATR 参数通常不构成新颖策略。",
    ),
}


FAMILY_TO_BASELINE_TAGS: dict[str, tuple[str, ...]] = {
    "trend_following": ("trend", "moving-average"),
    "mean_reversion": ("reversion", "oscillator"),
    "breakout": ("breakout",),
    "momentum_filter": ("momentum", "oscillator", "trend"),
    "volatility_filter": ("vectorized", "breakout"),
}


def get_strategy_knowledge_catalog() -> list[StrategyKnowledge]:
    return list(STRATEGY_KNOWLEDGE_CATALOG.values())


def get_strategy_knowledge(family_key: str) -> StrategyKnowledge:
    normalized = family_key.strip().lower()
    if normalized not in STRATEGY_KNOWLEDGE_CATALOG:
        raise KeyError(f"Unknown strategy knowledge family: {family_key}")
    return STRATEGY_KNOWLEDGE_CATALOG[normalized]


def knowledge_payload_for_market(market_scope: str) -> list[dict[str, object]]:
    market = market_scope.upper()
    return [item.to_dict() for item in get_strategy_knowledge_catalog() if market in item.supported_markets]


def knowledge_preferences_from_market_profile(
    *,
    preferred_baseline_tags: list[str] | tuple[str, ...],
    discouraged_baseline_tags: list[str] | tuple[str, ...],
) -> tuple[list[str], list[str]]:
    preferred = set(preferred_baseline_tags)
    discouraged = set(discouraged_baseline_tags)
    preferred_families: list[str] = []
    discouraged_families: list[str] = []
    for family_key, tags in FAMILY_TO_BASELINE_TAGS.items():
        if preferred.intersection(tags):
            preferred_families.append(family_key)
        if discouraged.intersection(tags):
            discouraged_families.append(family_key)
    return preferred_families, discouraged_families
