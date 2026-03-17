"""
市场与代码标准化工具
"""
from __future__ import annotations

import re


CN_TS_CODE_RE = re.compile(r"^\d{6}\.(SH|SZ)$", re.IGNORECASE)
CN_DIGIT_RE = re.compile(r"^\d{6}$")
HK_TICKER_RE = re.compile(r"^\d{1,5}(\.HK)?$", re.IGNORECASE)
US_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9\.\-]{0,9}$", re.IGNORECASE)


def detect_market(ticker: str) -> str:
    """
    检测市场类型: cn / hk / us
    """
    symbol = (ticker or "").strip().upper()
    if CN_TS_CODE_RE.match(symbol) or CN_DIGIT_RE.match(symbol):
        return "cn"
    if HK_TICKER_RE.match(symbol):
        return "hk"
    if US_TICKER_RE.match(symbol):
        return "us"
    return "us"


def normalize_cn_symbol(ticker: str) -> str:
    """
    统一为 tushare ts_code（如 600519.SH / 000001.SZ）
    """
    symbol = (ticker or "").strip().upper()
    if CN_TS_CODE_RE.match(symbol):
        return symbol
    if CN_DIGIT_RE.match(symbol):
        suffix = "SH" if symbol.startswith(("5", "6", "9")) else "SZ"
        return f"{symbol}.{suffix}"
    raise ValueError(f"Invalid CN symbol: {ticker}")


def normalize_hk_symbol(ticker: str) -> str:
    """
    统一为 4~5 位数字 + .HK（如 0700.HK）
    """
    symbol = (ticker or "").strip().upper()
    if symbol.endswith(".HK"):
        raw = symbol[:-3]
    else:
        raw = symbol
    if not raw.isdigit():
        return symbol
    return f"{raw.zfill(4)}.HK"


def normalize_tushare_symbol(ticker: str) -> str:
    """
    统一为 Tushare 可接受的 ts_code。

    - A股: 600519.SH / 000001.SZ
    - 港股: 02800.HK / 00700.HK
    """
    market = detect_market(ticker)
    if market == "cn":
        return normalize_cn_symbol(ticker)
    if market == "hk":
        symbol = (ticker or "").strip().upper()
        if symbol.endswith(".HK"):
            raw = symbol[:-3]
        else:
            raw = symbol
        if not raw.isdigit():
            raise ValueError(f"Invalid HK symbol for tushare/minshare: {ticker}")
        return f"{raw.zfill(5)}.HK"
    raise ValueError(f"Unsupported symbol for tushare: {ticker}")


def normalize_symbol(ticker: str, market: str | None = None) -> str:
    """
    按市场标准化代码
    """
    resolved_market = market or detect_market(ticker)
    if resolved_market == "cn":
        return normalize_cn_symbol(ticker)
    if resolved_market == "hk":
        return normalize_hk_symbol(ticker)
    return (ticker or "").strip().upper()
