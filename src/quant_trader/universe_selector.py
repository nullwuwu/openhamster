"""
A 股动态选股器
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from .data import get_source_manager
from .data.symbols import normalize_cn_symbol
from .data.tushare_provider import TushareProvider

logger = logging.getLogger("quant_trader.universe_selector")


@dataclass
class UniverseConfig:
    top_n: int = 20
    min_list_days: int = 120
    exclude_st: bool = True
    include_gem: bool = True
    candidate_limit: int = 300


class AStockUniverseSelector:
    """
    A股动态股票池
    """

    def __init__(self, config: UniverseConfig | None = None):
        self.config = config or UniverseConfig()
        self.source_manager = get_source_manager()

    def select(self, as_of_date: Optional[str] = None) -> list[str]:
        target_date = pd.to_datetime(as_of_date or datetime.now().strftime("%Y-%m-%d"))
        candidates = self._load_candidates(target_date=target_date)
        if not candidates:
            logger.warning("⚠️ 动态股票池为空，使用默认指数池")
            return ["000300.SH", "510300.SH", "159915.SZ"][: self.config.top_n]

        score_rows = []
        for symbol in candidates[: self.config.candidate_limit]:
            metrics = self._score_symbol(symbol=symbol, as_of_date=target_date)
            if metrics is not None:
                score_rows.append(metrics)

        if not score_rows:
            logger.warning("⚠️ 评分为空，使用候选池前N")
            return candidates[: self.config.top_n]

        df = pd.DataFrame(score_rows)
        for column in ["mom20", "mom60", "liquidity20", "inv_vol20"]:
            col_min = df[column].min()
            col_max = df[column].max()
            if col_max == col_min:
                df[f"n_{column}"] = 0.5
            else:
                df[f"n_{column}"] = (df[column] - col_min) / (col_max - col_min)

        df["score"] = (
            0.35 * df["n_mom20"]
            + 0.35 * df["n_mom60"]
            + 0.20 * df["n_liquidity20"]
            + 0.10 * df["n_inv_vol20"]
        )
        picked = df.sort_values("score", ascending=False).head(self.config.top_n)["symbol"].tolist()
        logger.info(f"✅ 动态选股完成: {len(picked)} 只")
        return picked

    def _load_candidates(self, target_date: pd.Timestamp) -> list[str]:
        try:
            provider = TushareProvider()
            basic = provider.fetch_stock_basic(list_status="L")
        except Exception as exc:
            logger.warning(f"⚠️ 加载 stock_basic 失败: {exc}")
            return []

        if basic.empty:
            return []

        basic = basic.copy()
        basic["list_date"] = pd.to_datetime(basic["list_date"], format="%Y%m%d", errors="coerce")
        basic = basic.dropna(subset=["ts_code", "name", "list_date"])

        min_date = target_date - timedelta(days=self.config.min_list_days)
        basic = basic[basic["list_date"] <= min_date]

        if self.config.exclude_st:
            basic = basic[~basic["name"].str.contains("ST", case=False, na=False)]

        allowed_prefixes = {"600", "601", "603", "605", "000", "001", "002"}
        if self.config.include_gem:
            allowed_prefixes.add("300")

        basic["prefix"] = basic["ts_code"].str.slice(0, 3)
        basic = basic[basic["prefix"].isin(allowed_prefixes)]

        symbols = sorted({normalize_cn_symbol(code) for code in basic["ts_code"].tolist()})
        return symbols

    def _score_symbol(self, symbol: str, as_of_date: pd.Timestamp) -> dict | None:
        start = (as_of_date - timedelta(days=180)).strftime("%Y-%m-%d")
        end = as_of_date.strftime("%Y-%m-%d")
        df = self.source_manager.fetch_ohlcv(symbol, start, end)
        if df is None or len(df) < 70:
            return None

        data = df.tail(70).copy()
        if data["close"].isnull().any():
            return None
        returns = data["close"].pct_change().dropna()
        if len(returns) < 40:
            return None

        close = data["close"]
        volume = data["volume"]
        mom20 = float(close.iloc[-1] / close.iloc[-20] - 1.0)
        mom60 = float(close.iloc[-1] / close.iloc[-60] - 1.0)
        liquidity20 = float((close.tail(20) * volume.tail(20)).mean())
        inv_vol20 = float(1.0 / max(returns.tail(20).std(), 1e-9))

        if not np.isfinite(mom20 + mom60 + liquidity20 + inv_vol20):
            return None

        return {
            "symbol": symbol,
            "mom20": mom20,
            "mom60": mom60,
            "liquidity20": liquidity20,
            "inv_vol20": inv_vol20,
        }
