from __future__ import annotations
import logging

from ..config import get_settings
from ..models import BacktestResult, ReviewOutput, Verdict

logger = logging.getLogger("goby_shrimp.reviewer")


def risk_gate_review(result: BacktestResult) -> ReviewOutput:
    settings = get_settings()
    hard_fails, yellow_flags = [], []

    # 🔴 硬红线
    if result.max_drawdown > settings.hard_gates.max_drawdown:
        hard_fails.append(
            f"MaxDD {result.max_drawdown:.1%} > "
            f"红线 {settings.hard_gates.max_drawdown:.0%}"
        )

    missing = [
        a for a in settings.hard_gates.required_assumptions
        if a not in result.assumptions
    ]
    if missing:
        hard_fails.append(f"假设缺失: {', '.join(missing)}")

    if result.data_years < settings.hard_gates.min_data_years:
        hard_fails.append(
            f"数据区间 {result.data_years}年 < "
            f"最低 {settings.hard_gates.min_data_years}年"
        )

    if hard_fails:
        logger.warning("❌ NO_GO: %s", hard_fails)
        return ReviewOutput(
            verdict=Verdict.NO_GO,
            hard_gates_failed=hard_fails,
            reasoning="触犯硬红线，一票否决",
        )

    # 🟡 黄线
    low, high = settings.yellow_flags.max_drawdown_warning_range
    if low <= result.max_drawdown <= high:
        yellow_flags.append(f"MaxDD {result.max_drawdown:.1%} 贴近红线区间")

    if result.cagr > settings.yellow_flags.suspiciously_high_cagr:
        yellow_flags.append(
            f"CAGR {result.cagr:.1%} 异常亮眼，疑似过拟合"
        )

    if (
        result.param_sensitivity
        and result.param_sensitivity > settings.yellow_flags.param_sensitivity_threshold
    ):
        yellow_flags.append(
            f"参数敏感性 {result.param_sensitivity:.0%} 过高"
        )

    if result.is_first_live and settings.yellow_flags.first_live_deployment:
        yellow_flags.append("首次实盘部署，必须人工确认")

    # 🟢 效用分
    # Calibrated for paper admission:
    # - Hard gates already remove catastrophic drawdown / bad data windows.
    # - Utility should clearly separate "positive and stable enough to try"
    #   from "not disastrous, but still economically weak".
    cagr_term = result.cagr * 100.0
    sharpe_term = result.sharpe * 4.0
    drawdown_penalty = result.max_drawdown * 100.0 * 0.20
    turnover_penalty = min(result.annual_turnover, 30.0) * 0.05
    score = round(cagr_term + sharpe_term - drawdown_penalty - turnover_penalty, 1)

    verdict = Verdict.GO if score >= 4.0 else Verdict.REVISE

    logger.info(
        "🟢 %s — utility=%.1f, yellow_flags=%s",
        verdict.value, score, yellow_flags,
    )

    return ReviewOutput(
        verdict=verdict,
        requires_human_approve=len(yellow_flags) > 0,
        yellow_flags_triggered=yellow_flags,
        utility_score=score,
        reasoning=f"效用分 {score}，阈值 4.0",
    )
