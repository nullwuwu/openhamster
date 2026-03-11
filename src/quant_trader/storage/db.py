"""
SQLite 数据库连接与表初始化
"""
import sqlite3
import logging
from pathlib import Path
from typing import Optional

from .models import Account, Position, Order, DailyNav
from ..config import get_settings

logger = logging.getLogger("quant_trader.storage")


class Database:
    """SQLite 数据库"""
    
    def __init__(self, db_path: str | None = None):
        settings = get_settings()
        self.db_path = db_path or settings.storage.paper_db_path
        self._conn: Optional[sqlite3.Connection] = None
    
    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn
    
    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def execute(self, sql: str, params=None):
        """执行 SQL"""
        cursor = self.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        self.conn.commit()
        return cursor
    
    def executemany(self, sql: str, params_list):
        """批量执行"""
        cursor = self.conn.cursor()
        cursor.executemany(sql, params_list)
        self.conn.commit()
        return cursor
    
    def fetchone(self, sql: str, params=None):
        """查询单条"""
        cursor = self.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor.fetchone()
    
    def fetchall(self, sql: str, params=None):
        """查询多条"""
        cursor = self.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor.fetchall()


def init_db(db_path: str | None = None) -> Database:
    """
    初始化数据库
    
    Args:
        db_path: 数据库路径
        
    Returns:
        Database 实例
    """
    db = Database(db_path)
    
    # accounts 表
    db.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY,
            cash REAL NOT NULL DEFAULT 0,
            total_equity REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    
    # positions 表
    db.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            avg_cost REAL NOT NULL DEFAULT 0,
            market_value REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            UNIQUE(symbol)
        )
    """)
    
    # orders 表
    db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'FILLED',
            created_at TEXT NOT NULL
        )
    """)
    
    # daily_nav 表
    db.execute("""
        CREATE TABLE IF NOT EXISTS daily_nav (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL UNIQUE,
            cash REAL NOT NULL,
            position_value REAL NOT NULL,
            total_equity REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    
    logger.info(f"✅ 数据库初始化完成: {db_path}")
    return db
