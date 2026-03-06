"""
存储模型定义

SQLite 表结构
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Account:
    """账户"""
    id: int = 1  # 单账户
    cash: float = 0.0
    total_equity: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()


@dataclass
class Position:
    """持仓"""
    id: Optional[int] = None
    symbol: str = ""
    quantity: int = 0
    avg_cost: float = 0.0
    market_value: float = 0.0
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()


@dataclass
class Order:
    """订单"""
    id: Optional[int] = None
    symbol: str = ""
    side: str = ""  # BUY / SELL
    quantity: int = 0
    price: float = 0.0
    amount: float = 0.0
    status: str = "FILLED"
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


@dataclass
class DailyNav:
    """每日净值"""
    id: Optional[int] = None
    trade_date: str = ""
    cash: float = 0.0
    position_value: float = 0.0
    total_equity: float = 0.0
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
