"""
数据仓库

提供 SQLite 表的 CRUD 操作
"""
import logging
from datetime import datetime
from typing import Optional, List

from .db import Database
from .models import Account, Position, Order, DailyNav

logger = logging.getLogger("quant_trader.storage")


class AccountRepository:
    """账户仓库"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get(self, account_id: int = 1) -> Optional[Account]:
        """获取账户"""
        row = self.db.fetchone(
            "SELECT * FROM accounts WHERE id = ?",
            (account_id,)
        )
        if row:
            return Account(
                id=row["id"],
                cash=row["cash"],
                total_equity=row["total_equity"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        return None
    
    def create(self, cash: float = 0.0) -> Account:
        """创建账户"""
        now = datetime.now().isoformat()
        self.db.execute(
            "INSERT INTO accounts (id, cash, total_equity, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (1, cash, cash, now, now)
        )
        return Account(id=1, cash=cash, total_equity=cash, created_at=now, updated_at=now)
    
    def update(self, account: Account):
        """更新账户"""
        account.updated_at = datetime.now().isoformat()
        self.db.execute(
            "UPDATE accounts SET cash = ?, total_equity = ?, updated_at = ? WHERE id = ?",
            (account.cash, account.total_equity, account.updated_at, account.id)
        )
    
    def get_or_create(self, initial_capital: float = 1_000_000) -> Account:
        """获取或创建"""
        account = self.get()
        if not account:
            account = self.create(initial_capital)
        return account


class PositionRepository:
    """持仓仓库"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        row = self.db.fetchone(
            "SELECT * FROM positions WHERE symbol = ?",
            (symbol,)
        )
        if row:
            return Position(
                id=row["id"],
                symbol=row["symbol"],
                quantity=row["quantity"],
                avg_cost=row["avg_cost"],
                market_value=row["market_value"],
                updated_at=row["updated_at"],
            )
        return None
    
    def get_all(self) -> List[Position]:
        """获取所有持仓"""
        rows = self.db.fetchall("SELECT * FROM positions WHERE quantity > 0")
        return [
            Position(
                id=row["id"],
                symbol=row["symbol"],
                quantity=row["quantity"],
                avg_cost=row["avg_cost"],
                market_value=row["market_value"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
    
    def upsert(self, position: Position):
        """更新或插入"""
        position.updated_at = datetime.now().isoformat()
        self.db.execute(
            """
            INSERT INTO positions (symbol, quantity, avg_cost, market_value, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                quantity = excluded.quantity,
                avg_cost = excluded.avg_cost,
                market_value = excluded.market_value,
                updated_at = excluded.updated_at
            """,
            (position.symbol, position.quantity, position.avg_cost, 
             position.market_value, position.updated_at)
        )
    
    def delete(self, symbol: str):
        """删除持仓"""
        self.db.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))


class OrderRepository:
    """订单仓库"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def create(self, order: Order) -> int:
        """创建订单"""
        self.db.execute(
            """
            INSERT INTO orders (symbol, side, quantity, price, amount, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (order.symbol, order.side, order.quantity, order.price,
             order.amount, order.status, order.created_at)
        )
        cursor = self.db.conn.cursor()
        return cursor.lastrowid
    
    def get_all(self, limit: int = 100) -> List[Order]:
        """获取订单列表"""
        rows = self.db.fetchall(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        return [
            Order(
                id=row["id"],
                symbol=row["symbol"],
                side=row["side"],
                quantity=row["quantity"],
                price=row["price"],
                amount=row["amount"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


class DailyNavRepository:
    """每日净值仓库"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get(self, trade_date: str) -> Optional[DailyNav]:
        """获取指定日期净值"""
        row = self.db.fetchone(
            "SELECT * FROM daily_nav WHERE trade_date = ?",
            (trade_date,)
        )
        if row:
            return DailyNav(
                id=row["id"],
                trade_date=row["trade_date"],
                cash=row["cash"],
                position_value=row["position_value"],
                total_equity=row["total_equity"],
                created_at=row["created_at"],
            )
        return None
    
    def exists(self, trade_date: str) -> bool:
        """检查是否存在"""
        row = self.db.fetchone(
            "SELECT 1 FROM daily_nav WHERE trade_date = ?",
            (trade_date,)
        )
        return row is not None
    
    def create(self, nav: DailyNav):
        """创建净值记录"""
        self.db.execute(
            """
            INSERT INTO daily_nav (trade_date, cash, position_value, total_equity, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (nav.trade_date, nav.cash, nav.position_value, 
             nav.total_equity, nav.created_at)
        )
    
    def get_latest(self) -> Optional[DailyNav]:
        """获取最新净值"""
        row = self.db.fetchone(
            "SELECT * FROM daily_nav ORDER BY trade_date DESC LIMIT 1"
        )
        if row:
            return DailyNav(
                id=row["id"],
                trade_date=row["trade_date"],
                cash=row["cash"],
                position_value=row["position_value"],
                total_equity=row["total_equity"],
                created_at=row["created_at"],
            )
        return None
    
    def get_all(self, limit: int = 30) -> List[DailyNav]:
        """获取净值历史"""
        rows = self.db.fetchall(
            "SELECT * FROM daily_nav ORDER BY trade_date DESC LIMIT ?",
            (limit,)
        )
        return [
            DailyNav(
                id=row["id"],
                trade_date=row["trade_date"],
                cash=row["cash"],
                position_value=row["position_value"],
                total_equity=row["total_equity"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
