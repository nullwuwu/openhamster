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
    "fundamental_growth": StrategyKnowledge(
        knowledge_id="knowledge_fundamental_growth_v1",
        family_key="fundamental_growth",
        label_zh="基本面成长",
        summary_zh="通过盈利增长、质量约束和估值纪律筛选中长期可持续的成长型标的。",
        core_logic_zh="先确认成长和财务质量，再结合估值和调仓节奏控制，把财务改善转成更稳定的持仓逻辑。",
        supported_markets=("HK", "CN"),
        preferred_market_conditions=("bullish", "orderly_expansion", "persistent_trend"),
        discouraged_market_conditions=("event_shock", "sharp_reversal", "liquidity_stress"),
        common_indicators=("revenue_growth", "earnings_growth", "ROE", "PEG", "PB"),
        common_failure_modes=("valuation_trap", "earnings_miss", "quality_deterioration"),
        parameter_priors={
            "min_revenue_growth": {"min": 0.05, "max": 0.5},
            "min_earnings_growth": {"min": 0.05, "max": 0.6},
            "max_peg": {"min": 0.4, "max": 2.5},
            "rebalance_days": {"min": 5, "max": 90},
        },
        risk_flags=("fundamental_data_lag", "valuation_compression", "crowded_quality"),
        related_baselines=(),
        novelty_expectation="合理变体应体现在成长质量、估值纪律或调仓节奏的组合变化；只换单个财务阈值通常不构成强新意。",
    ),
    "cross_sectional_ranking": StrategyKnowledge(
        knowledge_id="knowledge_cross_sectional_ranking_v1",
        family_key="cross_sectional_ranking",
        label_zh="横截面排序",
        summary_zh="先限定可交易股票池，再按一组评分因子对同一时点的标的横向排序选出前列。",
        core_logic_zh="收益来源不是单一指标，而是股票池裁剪、排序规则和换手控制共同作用下的相对强弱选择。",
        supported_markets=("HK", "CN"),
        preferred_market_conditions=("leadership_concentration", "orderly_expansion", "persistent_trend"),
        discouraged_market_conditions=("liquidity_stress", "chaotic_volatility", "sharp_reversal"),
        common_indicators=("market_cap", "turnover", "relative_strength", "quality_score", "composite_rank"),
        common_failure_modes=("crowding", "liquidity_thin_tail", "ranking_instability"),
        parameter_priors={
            "top_n": {"min": 3, "max": 50},
            "min_turnover_millions": {"min": 50, "max": 5000},
            "rebalance_days": {"min": 1, "max": 30},
        },
        risk_flags=("capacity_mismatch", "style_drift", "rank_overfit"),
        related_baselines=(),
        novelty_expectation="合理变体应说明排序因子和股票池约束如何协同；只是在同一排名框架里替换个别阈值通常不算强新策略。",
    ),
    "regime_filter": StrategyKnowledge(
        knowledge_id="knowledge_regime_filter_v1",
        family_key="regime_filter",
        label_zh="市场状态过滤",
        summary_zh="利用指数趋势、宽度、波动或宏观状态判断主策略当前是否应该启用、降仓或暂停。",
        core_logic_zh="它不独立产生收益，而是控制主策略何时参与市场，避免在已知不利环境里硬做信号。",
        supported_markets=("HK", "CN"),
        preferred_market_conditions=("persistent_trend", "orderly_expansion", "macro_tailwind"),
        discouraged_market_conditions=("event_shock", "chaotic_volatility", "macro_headwind"),
        common_indicators=("index_trend", "MACD", "breadth", "drawdown", "macro_bias"),
        common_failure_modes=("late_deactivation", "missed_reentry", "filter_conflict"),
        parameter_priors={
            "lookback_days": {"min": 5, "max": 120},
            "cooldown_days": {"min": 1, "max": 20},
            "breadth_threshold": {"min": 0.2, "max": 0.8},
        },
        risk_flags=("overfiltering", "macro_dependency", "timing_whipsaw"),
        related_baselines=(),
        novelty_expectation="合理变体应说明它如何保护主策略免受坏环境影响；把常见指数过滤器重新命名通常不构成新策略。",
    ),
    "portfolio_construction_overlay": StrategyKnowledge(
        knowledge_id="knowledge_portfolio_construction_overlay_v1",
        family_key="portfolio_construction_overlay",
        label_zh="组合构建覆盖层",
        summary_zh="通过持仓数量、权重分配、行业约束和风险预算把单一信号转成更可执行的投资组合。",
        core_logic_zh="收益不只取决于买什么，也取决于怎么分仓、怎么限制集中度，以及何时因为组合风险而降权。",
        supported_markets=("HK", "CN"),
        preferred_market_conditions=("orderly_expansion", "range_bound", "persistent_trend"),
        discouraged_market_conditions=("liquidity_stress", "event_shock"),
        common_indicators=("position_count", "weight_cap", "sector_limit", "turnover_budget"),
        common_failure_modes=("overconcentration", "hidden_factor_bet", "turnover_spike"),
        parameter_priors={
            "max_positions": {"min": 2, "max": 30},
            "max_weight": {"min": 0.03, "max": 0.5},
            "sector_cap": {"min": 0.1, "max": 0.7},
        },
        risk_flags=("concentration_risk", "rebalance_drag", "constraint_interaction"),
        related_baselines=(),
        novelty_expectation="合理变体应体现仓位分配或集中度控制逻辑的明确变化；只改持仓数上限通常不构成强创新。",
    ),
}


FAMILY_TO_BASELINE_TAGS: dict[str, tuple[str, ...]] = {
    "trend_following": ("trend", "moving-average"),
    "mean_reversion": ("reversion", "mean-reversion", "oscillator"),
    "breakout": ("breakout",),
    "momentum_filter": ("momentum", "oscillator", "trend"),
    "volatility_filter": ("vectorized", "breakout"),
    "fundamental_growth": ("quality", "growth", "valuation", "fundamental"),
    "cross_sectional_ranking": ("momentum", "ranking", "rotation", "small-cap"),
    "regime_filter": ("trend", "macro", "timing", "momentum"),
    "portfolio_construction_overlay": ("vectorized", "diversified", "portfolio", "risk-budget"),
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
