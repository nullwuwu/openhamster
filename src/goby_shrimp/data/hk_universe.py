from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from .symbols import normalize_symbol


def _pick_column(frame: pd.DataFrame, *names: str) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    if parsed != parsed:  # NaN
        return None
    return parsed


def _bounded(value: float, *, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _reason_tags(*, turnover_millions: float, change_pct: float, amplitude_pct: float | None, latest_price: float) -> list[str]:
    tags: list[str] = []
    if turnover_millions >= 3000:
        tags.append("very_high_liquidity")
    elif turnover_millions >= 1000:
        tags.append("high_liquidity")
    elif turnover_millions >= 400:
        tags.append("tradable_liquidity")

    if change_pct >= 1.5:
        tags.append("positive_momentum")
    elif change_pct <= -1.5:
        tags.append("negative_momentum")

    if amplitude_pct is not None:
        if amplitude_pct <= 4.0:
            tags.append("controlled_range")
        elif amplitude_pct >= 10.0:
            tags.append("volatile_range")

    if latest_price < 1.0:
        tags.append("penny_stock_penalty")
    elif latest_price >= 10.0:
        tags.append("institutional_price_band")

    return tags


def _apply_history_signals(candidate: dict[str, object], history: pd.DataFrame) -> None:
    factor_scores = dict(candidate.get("factor_scores", {}) or {})
    reason_tags = list(candidate.get("reason_tags", []) or [])

    if history is None or history.empty or "close" not in history.columns:
        factor_scores["history_quality"] = -10.0
        candidate["factor_scores"] = factor_scores
        reason_tags.append("history_gap_penalty")
        candidate["reason_tags"] = list(dict.fromkeys(reason_tags))
        candidate["score"] = round(float(candidate.get("score", 0.0) or 0.0) - 10.0, 2)
        return
    closes = pd.to_numeric(history["close"], errors="coerce").dropna()
    if len(closes) < 25:
        factor_scores["history_quality"] = -8.0
        candidate["factor_scores"] = factor_scores
        reason_tags.append("history_gap_penalty")
        candidate["reason_tags"] = list(dict.fromkeys(reason_tags))
        candidate["score"] = round(float(candidate.get("score", 0.0) or 0.0) - 8.0, 2)
        return

    latest_close = float(closes.iloc[-1])
    return_20d = ((latest_close / float(closes.iloc[-21])) - 1.0) * 100 if len(closes) >= 21 else None
    return_60d = ((latest_close / float(closes.iloc[-61])) - 1.0) * 100 if len(closes) >= 61 else None
    returns = closes.pct_change().dropna()
    volatility_20d = float(returns.tail(20).std() * 100) if len(returns) >= 20 else None

    trend_score = 0.0
    if return_20d is not None and return_60d is not None:
        if return_20d > 0 and return_60d > 0:
            reason_tags.append("trend_persistence")
            trend_score += 8.0
        elif return_20d < 0 and return_60d < 0:
            reason_tags.append("trend_decay")
            trend_score -= 6.0
    if return_20d is not None:
        trend_score += _bounded(return_20d * 0.45, lower=-8.0, upper=10.0)
    if return_60d is not None:
        trend_score += _bounded(return_60d * 0.2, lower=-6.0, upper=8.0)

    volatility_score = 0.0
    if volatility_20d is not None:
        if volatility_20d <= 1.6:
            reason_tags.append("stable_trend")
            volatility_score += 5.0
        elif volatility_20d >= 4.5:
            reason_tags.append("high_short_term_volatility")
            volatility_score -= 6.0
        volatility_score += _bounded(3.8 - volatility_20d, lower=-4.0, upper=4.0)

    factor_scores["history_quality"] = 6.0
    reason_tags.append("history_confirmed")
    factor_scores["trend_persistence"] = round(trend_score, 2)
    factor_scores["volatility_regime"] = round(volatility_score, 2)
    candidate["factor_scores"] = factor_scores
    candidate["return_20d_pct"] = round(return_20d, 2) if return_20d is not None else None
    candidate["return_60d_pct"] = round(return_60d, 2) if return_60d is not None else None
    candidate["volatility_20d_pct"] = round(volatility_20d, 2) if volatility_20d is not None else None
    candidate["reason_tags"] = list(dict.fromkeys(reason_tags))
    candidate["score"] = round(float(candidate.get("score", 0.0) or 0.0) + trend_score + volatility_score, 2)

def _selection_reason(tags: list[str]) -> str:
    mapping = {
        "very_high_liquidity": "Very high turnover supports entry and exit capacity.",
        "high_liquidity": "High turnover supports stable execution.",
        "tradable_liquidity": "Turnover is sufficient for tradable size.",
        "positive_momentum": "Recent positive price action supports near-term strength.",
        "negative_momentum": "Recent weakness increases reversal or breakdown risk.",
        "controlled_range": "Intraday range is controlled rather than disorderly.",
        "volatile_range": "Intraday range is wide and raises execution risk.",
        "penny_stock_penalty": "Sub-1 HKD price weakens price quality.",
        "institutional_price_band": "Price band is consistent with institutional trading preference.",
        "trend_persistence": "Multi-week price trend remains intact across recent windows.",
        "trend_decay": "Recent and medium-term trend both weaken the setup.",
        "stable_trend": "Short-term volatility remains stable enough for cleaner execution.",
        "high_short_term_volatility": "Short-term volatility is elevated and can destabilize entries.",
        "history_confirmed": "Recent multi-week history is available and supports ranking confidence.",
        "history_gap_penalty": "Limited recent history reduces ranking confidence for this symbol.",
    }
    preferred_order = [
        "very_high_liquidity",
        "high_liquidity",
        "tradable_liquidity",
        "positive_momentum",
        "controlled_range",
        "institutional_price_band",
        "trend_persistence",
        "stable_trend",
        "history_confirmed",
        "negative_momentum",
        "trend_decay",
        "high_short_term_volatility",
        "history_gap_penalty",
        "volatile_range",
        "penny_stock_penalty",
    ]
    selected = [mapping[tag] for tag in preferred_order if tag in tags][:3]
    return " ".join(selected) if selected else "Selected as the best available HK candidate after liquidity and stability screening."


def fetch_hk_universe_candidates(*, top_n: int, min_turnover_millions: float) -> list[dict[str, object]]:
    import akshare as ak

    frame = ak.stock_hk_spot_em()
    if frame is None or frame.empty:
        return []

    code_col = _pick_column(frame, "代码", "symbol", "代码 ")
    name_col = _pick_column(frame, "名称", "name")
    price_col = _pick_column(frame, "最新价", "close", "现价")
    pct_col = _pick_column(frame, "涨跌幅", "pct_chg", "涨跌幅%")
    amount_col = _pick_column(frame, "成交额", "amount")
    amplitude_col = _pick_column(frame, "振幅", "amplitude")
    if code_col is None or name_col is None:
        return []

    candidates: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        raw_code = str(row.get(code_col, "")).strip()
        if not raw_code.isdigit():
            continue
        symbol = normalize_symbol(f"{raw_code}.HK", market="hk")
        latest_price = _to_float(row.get(price_col)) if price_col else None
        change_pct = _to_float(row.get(pct_col)) if pct_col else None
        amount_value = _to_float(row.get(amount_col)) if amount_col else None
        amplitude_pct = _to_float(row.get(amplitude_col)) if amplitude_col else None
        turnover_millions = round((amount_value or 0.0) / 1_000_000, 2)
        if latest_price is None or latest_price <= 0:
            continue
        if turnover_millions < min_turnover_millions:
            continue

        liquidity_score = _bounded(
            20.0 + math.log10(max(turnover_millions / max(min_turnover_millions, 1.0), 1.0)) * 22.0,
            lower=10.0,
            upper=55.0,
        )
        momentum_score = _bounded((change_pct or 0.0) * 3.0, lower=-12.0, upper=18.0)
        stability_score = 12.0
        if amplitude_pct is not None:
            stability_score = _bounded(14.0 - max(amplitude_pct - 3.0, 0.0) * 1.8, lower=0.0, upper=14.0)
        price_quality_score = _bounded(10.0 if latest_price >= 1.0 else latest_price * 10.0, lower=0.0, upper=10.0)
        score = liquidity_score + momentum_score + stability_score + price_quality_score
        reason_tags = _reason_tags(
            turnover_millions=turnover_millions,
            change_pct=round(change_pct or 0.0, 2),
            amplitude_pct=round(amplitude_pct, 2) if amplitude_pct is not None else None,
            latest_price=latest_price,
        )
        candidates.append(
            {
                "symbol": symbol,
                "name": str(row.get(name_col, symbol)).strip() or symbol,
                "latest_price": round(latest_price, 4),
                "change_pct": round(change_pct or 0.0, 2),
                "amplitude_pct": round(amplitude_pct, 2) if amplitude_pct is not None else None,
                "turnover_millions": turnover_millions,
                "score": round(score, 2),
                "factor_scores": {
                    "liquidity": round(liquidity_score, 2),
                    "momentum": round(momentum_score, 2),
                    "stability": round(stability_score, 2),
                    "price_quality": round(price_quality_score, 2),
                },
                "reason_tags": reason_tags,
                "selection_reason": _selection_reason(reason_tags),
                "source": "akshare",
            }
        )

    candidates.sort(key=lambda item: (float(item["score"]), float(item["turnover_millions"])), reverse=True)

    enrich_limit = min(max(top_n * 2, 8), len(candidates))
    if enrich_limit > 0:
        from .source_manager import get_source_manager

        source_manager = get_source_manager()
        history_start = (datetime.now() - timedelta(days=150)).date().isoformat()
        history_end = datetime.now().date().isoformat()
        for candidate in candidates[:enrich_limit]:
            try:
                history = source_manager.fetch_ohlcv(str(candidate["symbol"]), history_start, history_end)
            except Exception:
                history = None
            _apply_history_signals(candidate, history if history is not None else pd.DataFrame())
            candidate["selection_reason"] = _selection_reason(list(candidate.get("reason_tags", [])))

    candidates.sort(key=lambda item: (float(item["score"]), float(item["turnover_millions"])), reverse=True)
    ranked = candidates[: max(1, top_n)]
    for index, candidate in enumerate(ranked, start=1):
        candidate["rank"] = index
    return ranked
