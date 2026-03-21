from __future__ import annotations

from openhamster.api.services import _knowledge_assessment
from openhamster.market_profile import get_market_profile


def _snapshot(regime: str = "BULLISH", volatility: float = 0.03, trend_strength: float = 0.13) -> dict[str, object]:
    return {
        "regime": regime,
        "price_context": {
            "volatility": volatility,
            "trend_strength": trend_strength,
        },
        "market_profile": get_market_profile("HK").to_dict(),
    }


def test_knowledge_assessment_flags_rule_stack_and_capacity_gaps() -> None:
    assessment = _knowledge_assessment(
        {
            "base_strategy": "novel_composite",
            "knowledge_families_used": [
                "fundamental_growth",
                "cross_sectional_ranking",
                "regime_filter",
                "portfolio_construction_overlay",
            ],
            "thesis": "结合成长、排序、状态过滤和组合约束寻找更稳健机会。",
            "baseline_delta_summary": "叠加多个过滤和排序层。",
            "novelty_claim": "多层组合创新。",
            "features_used": ["SMA", "EMA", "MACD", "ATR", "ROC"],
            "params": {
                "top_n": 12,
                "rebalance_days": 5,
                "lookback_days": 20,
                "cooldown_days": 4,
                "max_positions": 8,
                "max_weight": 0.18,
            },
        },
        _snapshot(),
    )

    assert assessment["rule_stack_complexity"] == "high"
    assert assessment["capacity_assumption_clarity"] == "unclear"
    assert assessment["regime_dependency_strength"] == "high"
    assert "knowledge_rule_stack_overfit" in assessment["blocked_reasons"]
    assert "knowledge_capacity_unclear" in assessment["blocked_reasons"]


def test_knowledge_assessment_accepts_clear_capacity_explanation() -> None:
    assessment = _knowledge_assessment(
        {
            "base_strategy": "novel_composite",
            "knowledge_families_used": [
                "cross_sectional_ranking",
                "portfolio_construction_overlay",
            ],
            "thesis": "先按流动性和相对强弱做排序，再限制持仓数、单票权重和行业分散，控制换手与容量。",
            "baseline_delta_summary": "强调成交额门槛、仓位上限和分散约束，而不是简单堆叠规则。",
            "novelty_claim": "将排序和组合构建结合为低换手候选框架。",
            "features_used": ["ROC", "Volume MA", "drawdown"],
            "params": {
                "top_n": 10,
                "max_positions": 6,
                "max_weight": 0.16,
            },
        },
        _snapshot(trend_strength=0.08),
    )

    assert assessment["capacity_assumption_clarity"] == "clear"
    assert assessment["rule_stack_complexity"] in {"low", "moderate"}
    assert "knowledge_capacity_unclear" not in assessment["blocked_reasons"]
