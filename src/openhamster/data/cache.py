"""
OHLCV 本地增量缓存
"""
from __future__ import annotations

import sqlite3
from datetime import timedelta
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
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

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

    def get_date_bounds(self, symbol: str) -> tuple[str | None, str | None]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT MIN(trade_date), MAX(trade_date)
                FROM ohlcv_cache
                WHERE symbol = ?
                """,
                (symbol,),
            ).fetchone()
        if not row:
            return None, None
        earliest = str(row[0]) if row[0] is not None else None
        latest = str(row[1]) if row[1] is not None else None
        return earliest, latest

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
        tolerated_gap_days = 3
        cached = self.get_range(symbol=symbol, start=start, end=end)
        earliest_date, last_date = self.get_date_bounds(symbol)
        if (
            earliest_date is not None
            and last_date is not None
            and earliest_date <= start
            and last_date >= end
            and not cached.empty
        ):
            return cached

        if earliest_date is None or last_date is None:
            try:
                loaded = loader(start, end)
            except Exception:
                loaded = None
            if loaded is not None and not loaded.empty:
                self.upsert(symbol=symbol, df=loaded)
            return self.get_range(symbol=symbol, start=start, end=end)

        if start < earliest_date:
            earliest_ts = pd.Timestamp(earliest_date)
            requested_start = pd.Timestamp(start)
            head_gap_days = max(0, (earliest_ts - requested_start).days)
            head_end = (earliest_ts - timedelta(days=1)).strftime("%Y-%m-%d")
            if start <= head_end:
                if head_gap_days > tolerated_gap_days:
                    try:
                        head_loaded = loader(start, head_end)
                    except Exception:
                        head_loaded = None
                    if head_loaded is not None and not head_loaded.empty:
                        self.upsert(symbol=symbol, df=head_loaded)

        if last_date < end:
            last_ts = pd.Timestamp(last_date)
            requested_end = pd.Timestamp(end)
            tail_gap_days = max(0, (requested_end - last_ts).days)
            tail_start = (last_ts + timedelta(days=1)).strftime("%Y-%m-%d")
            if tail_start <= end and tail_gap_days > tolerated_gap_days:
                try:
                    tail_loaded = loader(tail_start, end)
                except Exception:
                    tail_loaded = None
                if tail_loaded is not None and not tail_loaded.empty:
                    self.upsert(symbol=symbol, df=tail_loaded)
        return self.get_range(symbol=symbol, start=start, end=end)
