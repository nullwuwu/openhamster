"""
OHLCV 本地增量缓存
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

import pandas as pd

from ..config import get_settings


class OHLCVCache:
    """基于 SQLite 的 K 线缓存"""

    def __init__(self, db_path: str | None = None):
        settings = get_settings()
        self.db_path = Path(db_path or settings.storage.market_cache_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ohlcv_cache (
                    symbol TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    PRIMARY KEY (symbol, trade_date)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_date ON ohlcv_cache(symbol, trade_date)"
            )

    def get_range(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        with self._connect() as conn:
            df = pd.read_sql_query(
                """
                SELECT trade_date AS date, open, high, low, close, volume
                FROM ohlcv_cache
                WHERE symbol = ? AND trade_date >= ? AND trade_date <= ?
                ORDER BY trade_date ASC
                """,
                conn,
                params=(symbol, start, end),
            )
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return df

    def get_last_trade_date(self, symbol: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT trade_date
                FROM ohlcv_cache
                WHERE symbol = ?
                ORDER BY trade_date DESC
                LIMIT 1
                """,
                (symbol,),
            ).fetchone()
        if row:
            return str(row[0])
        return None

    def upsert(self, symbol: str, df: pd.DataFrame) -> None:
        if df.empty:
            return
        working = df.copy()
        if "date" not in working.columns:
            working = working.reset_index().rename(columns={working.index.name or "index": "date"})
        working["date"] = pd.to_datetime(working["date"]).dt.strftime("%Y-%m-%d")
        rows = [
            (
                symbol,
                str(row["date"]),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["volume"]),
            )
            for _, row in working.iterrows()
        ]
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO ohlcv_cache(symbol, trade_date, open, high, low, close, volume)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, trade_date) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume
                """,
                rows,
            )

    def fetch_or_load(
        self,
        symbol: str,
        start: str,
        end: str,
        loader: Callable[[str, str], pd.DataFrame | None],
    ) -> pd.DataFrame:
        cached = self.get_range(symbol=symbol, start=start, end=end)
        last_date = self.get_last_trade_date(symbol)
        if last_date is not None and last_date >= end and not cached.empty:
            return cached
        load_start = start if last_date is None else max(start, last_date)
        loaded = loader(load_start, end)
        if loaded is not None and not loaded.empty:
            self.upsert(symbol=symbol, df=loaded)
        return self.get_range(symbol=symbol, start=start, end=end)
