from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import get_settings
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


_HISTORY_FAILURE_TTL_HOURS = 12
_HISTORY_FAILURE_CACHE_LIMIT = 512
_MAX_HISTORY_ENRICH_CANDIDATES = 12
_RESILIENT_HK_FALLBACK_SYMBOLS = [
    "0700.HK",
    "9988.HK",
    "3690.HK",
    "9618.HK",
    "1810.HK",
    "0388.HK",
    "0941.HK",
    "1299.HK",
    "2318.HK",
    "0005.HK",
    "1211.HK",
    "2388.HK",
    "0939.HK",
    "3988.HK",
    "0001.HK",
    "0011.HK",
    "0669.HK",
    "0762.HK",
    "1928.HK",
    "2800.HK",
]


def _history_failure_cache_path() -> Path:
    cache_path = Path(get_settings().storage.market_cache_path)
    return cache_path.parent / "hk_history_failures.json"


def _load_history_failure_memory() -> dict[str, str]:
    path = _history_failure_cache_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if str(key).strip() and str(value).strip()}


def _save_history_failure_memory(payload: dict[str, str]) -> None:
    path = _history_failure_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = dict(sorted(payload.items(), key=lambda item: item[1], reverse=True)[:_HISTORY_FAILURE_CACHE_LIMIT])
    path.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8")


def _prune_history_failure_memory(payload: dict[str, str]) -> dict[str, str]:
    if not payload:
        return {}
    cutoff = datetime.now() - timedelta(hours=_HISTORY_FAILURE_TTL_HOURS)
    kept: dict[str, str] = {}
    for symbol, failed_at in payload.items():
        try:
            failed_dt = datetime.fromisoformat(str(failed_at))
        except ValueError:
            continue
        if failed_dt >= cutoff:
            kept[symbol] = failed_dt.isoformat()
    return kept


def _has_recent_history_failure(memory: dict[str, str], symbol: str) -> bool:
    failed_at = memory.get(symbol)
    if not failed_at:
        return False
    try:
        failed_dt = datetime.fromisoformat(str(failed_at))
    except ValueError:
        return False
    return failed_dt >= datetime.now() - timedelta(hours=_HISTORY_FAILURE_TTL_HOURS)


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


def _lot_cost(symbol: str, latest_price: float) -> float:
    normalized = normalize_symbol(symbol, market="hk")
    lot_size = 100 if normalized.endswith(".HK") else 1
    return round(lot_size * latest_price, 2)


def _is_ordinary_hk_equity(*, name: str, fullname: str | None, market: str | None) -> bool:
    resolved_market = str(market or "").strip()
    if resolved_market and resolved_market not in {"主板", "创业板"}:
        return False

    combined = f"{name} {fullname or ''}".upper()
    exclusion_terms = [
        "ETF",
        "ETP",
        "REIT",
        "TRUST",
        "FUND",
        "INDEX",
        "BOND",
        "杠杆",
        "反向",
        "基金",
        "房托",
        "信托",
        "债",
        "货币",
        "期货",
        "牛熊",
    ]
    return not any(term in combined for term in exclusion_terms)


def _fetch_minshare_market_frame(min_list_days: int) -> pd.DataFrame:
    from .minshare_provider import MinShareProvider

    provider = MinShareProvider()
    basics = provider.fetch_hk_basic()
    if basics is None or basics.empty:
        return pd.DataFrame()

    basic_frame = basics.copy()
    basic_frame["ts_code"] = basic_frame["ts_code"].astype(str).str.upper().str.strip()
    basic_frame = basic_frame[basic_frame["list_status"].astype(str).str.upper() == "L"]
    basic_frame = basic_frame[
        basic_frame.apply(
            lambda row: _is_ordinary_hk_equity(
                name=str(row.get("name", "")).strip(),
                fullname=str(row.get("fullname", "")).strip() or None,
                market=str(row.get("market", "")).strip() or None,
            ),
            axis=1,
        )
    ]

    if min_list_days > 0 and "list_date" in basic_frame.columns:
        cutoff = (datetime.now() - timedelta(days=min_list_days)).strftime("%Y%m%d")
        basic_frame = basic_frame[
            basic_frame["list_date"].astype(str).str.fullmatch(r"\d{8}") & (basic_frame["list_date"].astype(str) <= cutoff)
        ]

    realtime_frames: list[pd.DataFrame] = []
    for prefix in [f"{index:02d}" for index in range(10)]:
        try:
            frame = provider.fetch_hk_rt_daily(f"{prefix}*.HK")
        except Exception:
            continue
        if frame is None or frame.empty:
            continue
        realtime_frames.append(frame.copy())

    if not realtime_frames:
        return pd.DataFrame()

    realtime = pd.concat(realtime_frames, ignore_index=True)
    realtime["ts_code"] = realtime["ts_code"].astype(str).str.upper().str.strip()
    realtime = realtime.drop_duplicates(subset=["ts_code"], keep="last")
    merged = realtime.merge(basic_frame, on="ts_code", how="inner", suffixes=("", "_basic"))
    return merged


def _fetch_akshare_market_frame() -> pd.DataFrame:
    import akshare as ak

    frame = ak.stock_hk_spot_em()
    if frame is None or frame.empty:
        return pd.DataFrame()
    return frame


def _apply_history_signals(candidate: dict[str, object], history: pd.DataFrame) -> None:
    factor_scores = dict(candidate.get("factor_scores", {}) or {})
    reason_tags = list(candidate.get("reason_tags", []) or [])
    candidate["history_available"] = False

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

    candidate["history_available"] = True
    latest_close = float(closes.iloc[-1])
    return_20d = ((latest_close / float(closes.iloc[-21])) - 1.0) * 100 if len(closes) >= 21 else None
    return_60d = ((latest_close / float(closes.iloc[-61])) - 1.0) * 100 if len(closes) >= 61 else None
    returns = closes.pct_change().dropna()
    volatility_20d = float(returns.tail(20).std() * 100) if len(returns) >= 20 else None
    rolling_peak = closes.cummax()
    drawdowns = (closes / rolling_peak) - 1.0
    max_drawdown_120d = float(drawdowns.tail(120).min() * -100) if len(drawdowns) >= 60 else None
    max_drawdown_250d = float(drawdowns.tail(250).min() * -100) if len(drawdowns) >= 120 else None

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
            volatility_score -= 14.0
        volatility_score += _bounded(3.8 - volatility_20d, lower=-4.0, upper=4.0)

    crowding_score = 0.0
    if return_20d is not None and return_20d >= 25.0:
        reason_tags.append("overextended_short_term")
        crowding_score -= _bounded((return_20d - 25.0) * 0.35, lower=6.0, upper=16.0)
    if return_60d is not None and return_60d >= 55.0:
        reason_tags.append("crowded_trend")
        crowding_score -= _bounded((return_60d - 55.0) * 0.18, lower=4.0, upper=12.0)

    drawdown_score = 0.0
    drawdown_reference = max_drawdown_250d if max_drawdown_250d is not None else max_drawdown_120d
    candidate["drawdown_flagged"] = False
    if drawdown_reference is not None:
        if drawdown_reference <= 12.0:
            reason_tags.append("resilient_drawdown_profile")
            drawdown_score += 8.0
        elif drawdown_reference >= 22.0:
            reason_tags.append("historical_drawdown_risk")
            candidate["drawdown_flagged"] = True
            drawdown_score -= _bounded((drawdown_reference - 22.0) * 0.9, lower=14.0, upper=24.0)
        elif drawdown_reference >= 16.0:
            reason_tags.append("elevated_drawdown_profile")
            drawdown_score -= _bounded((drawdown_reference - 16.0) * 1.5, lower=8.0, upper=16.0)

    factor_scores["history_quality"] = 6.0
    reason_tags.append("history_confirmed")
    factor_scores["trend_persistence"] = round(trend_score, 2)
    factor_scores["volatility_regime"] = round(volatility_score, 2)
    factor_scores["crowding_penalty"] = round(crowding_score, 2)
    factor_scores["drawdown_profile"] = round(drawdown_score, 2)
    candidate["factor_scores"] = factor_scores
    candidate["return_20d_pct"] = round(return_20d, 2) if return_20d is not None else None
    candidate["return_60d_pct"] = round(return_60d, 2) if return_60d is not None else None
    candidate["volatility_20d_pct"] = round(volatility_20d, 2) if volatility_20d is not None else None
    candidate["max_drawdown_120d_pct"] = round(max_drawdown_120d, 2) if max_drawdown_120d is not None else None
    candidate["max_drawdown_250d_pct"] = round(max_drawdown_250d, 2) if max_drawdown_250d is not None else None
    candidate["reason_tags"] = list(dict.fromkeys(reason_tags))
    candidate["score"] = round(float(candidate.get("score", 0.0) or 0.0) + trend_score + volatility_score + crowding_score + drawdown_score, 2)

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
        "overextended_short_term": "Recent run-up is overextended and can invite sharp mean reversion.",
        "crowded_trend": "Crowded medium-term trend can reverse violently after momentum exhaustion.",
        "resilient_drawdown_profile": "Recent historical drawdown stayed contained and improves governance fit.",
        "elevated_drawdown_profile": "Historical drawdown is elevated and weakens paper-admission odds.",
        "historical_drawdown_risk": "Historical drawdown is too deep and often fails current risk gates.",
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
        "overextended_short_term",
        "crowded_trend",
        "resilient_drawdown_profile",
        "elevated_drawdown_profile",
        "historical_drawdown_risk",
        "history_gap_penalty",
        "volatile_range",
        "penny_stock_penalty",
    ]
    selected = [mapping[tag] for tag in preferred_order if tag in tags][:3]
    return " ".join(selected) if selected else "Selected as the best available HK candidate after liquidity and stability screening."


def _fetch_resilient_hk_fallback_frame(min_turnover_millions: float) -> pd.DataFrame:
    from .stooq_provider import StooqProvider
    from .tencent_provider import TencentProvider

    tencent = TencentProvider(max_retries=1)
    stooq = StooqProvider(max_retries=1)
    now = datetime.now()
    start = (now - timedelta(days=15)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    rows: list[dict[str, object]] = []
    for symbol in _RESILIENT_HK_FALLBACK_SYMBOLS[:12]:
        history = None
        try:
            history = tencent.fetch_ohlcv(symbol, start, end)
        except Exception:
            try:
                history = stooq.fetch_ohlcv(symbol, start, end)
            except Exception:
                history = None
        if history is None or history.empty or "close" not in history.columns:
            continue
        closes = pd.to_numeric(history["close"], errors="coerce").dropna()
        if len(closes) < 2:
            continue
        latest_price = float(closes.iloc[-1])
        previous_price = float(closes.iloc[-2])
        change_pct = ((latest_price / previous_price) - 1.0) * 100 if previous_price else 0.0
        returns = closes.pct_change().dropna()
        amplitude_pct = float(returns.tail(5).abs().mean() * 100) if not returns.empty else None
        volume_series = pd.to_numeric(history.get("volume"), errors="coerce").dropna()
        turnover_millions = 0.0
        if not volume_series.empty:
            turnover_millions = round(float(volume_series.tail(5).mean()) * latest_price / 1_000_000, 2)
        if turnover_millions < min_turnover_millions:
            turnover_millions = max(min_turnover_millions, round(turnover_millions, 2))
        rows.append(
            {
                "symbol": symbol.replace(".HK", ""),
                "name": symbol,
                "close": latest_price,
                "pct_chg": round(change_pct, 2),
                "amount": turnover_millions * 1_000_000,
                "amplitude": round(amplitude_pct, 2) if amplitude_pct is not None else None,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def fetch_hk_universe_candidates(
    *,
    top_n: int,
    min_list_days: int,
    min_turnover_millions: float,
    account_capital_hkd: float,
    max_lot_cost_ratio: float,
) -> list[dict[str, object]]:
    frame = pd.DataFrame()
    source_name = "minshare_rt"
    minshare_error: Exception | None = None
    try:
        frame = _fetch_minshare_market_frame(min_list_days)
    except Exception as exc:
        minshare_error = exc
    if frame is None or frame.empty:
        source_name = "akshare"
        try:
            frame = _fetch_akshare_market_frame()
        except Exception:
            frame = pd.DataFrame()
    if frame is None or frame.empty:
        source_name = "resilient_fallback"
        frame = _fetch_resilient_hk_fallback_frame(min_turnover_millions)
    if frame is None or frame.empty:
        if minshare_error is not None:
            raise RuntimeError(f"minshare universe failed: {minshare_error}")
        return []

    code_col = _pick_column(frame, "代码", "symbol", "代码 ", "ts_code")
    name_col = _pick_column(frame, "名称", "name")
    price_col = _pick_column(frame, "最新价", "close", "现价")
    pct_col = _pick_column(frame, "涨跌幅", "pct_chg", "涨跌幅%")
    amount_col = _pick_column(frame, "成交额", "amount")
    amplitude_col = _pick_column(frame, "振幅", "amplitude")
    trade_unit_col = _pick_column(frame, "trade_unit")
    if code_col is None or name_col is None:
        return []

    candidates: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        raw_code = str(row.get(code_col, "")).strip()
        if raw_code.upper().endswith(".HK"):
            raw_code = raw_code[:-3]
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
        trade_unit = int(_to_float(row.get(trade_unit_col)) or 100) if trade_unit_col else 100
        lot_cost_hkd = round(trade_unit * latest_price, 2)
        affordability_ratio = lot_cost_hkd / max(account_capital_hkd, 1.0)
        if lot_cost_hkd > account_capital_hkd or affordability_ratio > max_lot_cost_ratio:
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
                "lot_cost_hkd": lot_cost_hkd,
                "affordability_ratio": round(affordability_ratio, 4),
                "score": round(score, 2),
                "factor_scores": {
                    "liquidity": round(liquidity_score, 2),
                    "momentum": round(momentum_score, 2),
                    "stability": round(stability_score, 2),
                    "price_quality": round(price_quality_score, 2),
                },
                "reason_tags": reason_tags,
                "selection_reason": _selection_reason(reason_tags),
                "source": source_name,
            }
        )

    candidates.sort(key=lambda item: (float(item["score"]), float(item["turnover_millions"])), reverse=True)

    research_batch_size = max(1, int(get_settings().universe.research_batch_size))
    enrich_limit = min(
        max(research_batch_size * 3, 8),
        min(_MAX_HISTORY_ENRICH_CANDIDATES, len(candidates)),
    )
    if enrich_limit > 0:
        from .source_manager import get_source_manager

        source_manager = get_source_manager()
        history_start = (datetime.now() - timedelta(days=420)).date().isoformat()
        history_end = datetime.now().date().isoformat()
        history_failure_memory = _prune_history_failure_memory(_load_history_failure_memory())
        history_failure_dirty = False
        for candidate in candidates[:enrich_limit]:
            symbol = str(candidate["symbol"])
            if _has_recent_history_failure(history_failure_memory, symbol):
                candidate["recent_history_failure"] = True
                factor_scores = dict(candidate.get("factor_scores", {}) or {})
                factor_scores["history_fetch_penalty"] = -12.0
                candidate["factor_scores"] = factor_scores
                reason_tags = list(candidate.get("reason_tags", []) or [])
                reason_tags.extend(["history_gap_penalty", "recent_history_source_failure"])
                candidate["reason_tags"] = list(dict.fromkeys(reason_tags))
                candidate["score"] = round(float(candidate.get("score", 0.0) or 0.0) - 12.0, 2)
                candidate["selection_reason"] = _selection_reason(list(candidate.get("reason_tags", [])))
                continue
            try:
                history = source_manager.fetch_ohlcv(symbol, history_start, history_end)
            except Exception:
                history = None
            if history is None or history.empty:
                candidate["recent_history_failure"] = True
                history_failure_memory[symbol] = datetime.now().isoformat()
                history_failure_dirty = True
            elif symbol in history_failure_memory:
                candidate["recent_history_failure"] = False
                history_failure_memory.pop(symbol, None)
                history_failure_dirty = True
            else:
                candidate["recent_history_failure"] = False
            _apply_history_signals(candidate, history if history is not None else pd.DataFrame())
            candidate["selection_reason"] = _selection_reason(list(candidate.get("reason_tags", [])))
        if history_failure_dirty:
            _save_history_failure_memory(_prune_history_failure_memory(history_failure_memory))

    candidates.sort(
        key=lambda item: (
            bool(item.get("history_available", False)),
            not bool(item.get("drawdown_flagged", False)),
            float(item["score"]),
            float(item["turnover_millions"]),
        ),
        reverse=True,
    )
    history_confirmed = [
        item
        for item in candidates
        if bool(item.get("history_available", False)) and not bool(item.get("drawdown_flagged", False))
    ]
    history_flagged = [
        item
        for item in candidates
        if bool(item.get("history_available", False)) and bool(item.get("drawdown_flagged", False))
    ]
    fallback_pool = [
        item
        for item in candidates
        if not bool(item.get("history_available", False)) and not bool(item.get("recent_history_failure", False))
    ]
    recent_failure_pool = [
        item
        for item in candidates
        if not bool(item.get("history_available", False)) and bool(item.get("recent_history_failure", False))
    ]
    ranked = (
        history_confirmed[: max(1, top_n)]
        + history_flagged[: max(0, top_n - len(history_confirmed[: max(1, top_n)]))]
        + fallback_pool[: max(0, top_n - len(history_confirmed[: max(1, top_n)]) - len(history_flagged[: max(0, top_n - len(history_confirmed[: max(1, top_n)]))]))]
        + recent_failure_pool[: max(0, top_n)]
    )[: max(1, top_n)]
    for index, candidate in enumerate(ranked, start=1):
        candidate["rank"] = index
    return ranked
