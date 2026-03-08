"""
订单防护机制 - 防止重复下单

在 Agent 层面增加额外保护
"""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional
from pathlib import Path
import json

logger = logging.getLogger("quant_trader.order_guard")


@dataclass
class OrderRecord:
    """订单记录"""
    symbol: str
    side: str  # BUY / SELL
    qty: int
    price: float
    timestamp: float
    order_id: str = ""
    status: str = "pending"  # pending/filled/cancelled


@dataclass
class OrderGuardReport:
    """订单防护报告"""
    allowed: bool
    reason: str
    cooldown_remaining: float = 0  # 秒
    today_count: int = 0
    symbol_count: int = 0
    last_order: Optional[OrderRecord] = None


class OrderGuard:
    """
    重复下单防护器
    
    防护规则:
    1. 同股票同方向冷却时间 (默认 5 分钟)
    2. 单日最大交易次数 (默认 3 次)
    3. 单股票单日最大交易次数 (默认 2 次)
    """
    
    def __init__(
        self,
        cooldown_seconds: int = 300,      # 5 分钟冷却
        max_daily_orders: int = 3,         # 每日最多 3 次
        max_per_symbol: int = 2,           # 每股票每日最多 2 次
        data_dir: str = None,
    ):
        """
        Args:
            cooldown_seconds: 同方向订单冷却时间
            max_daily_orders: 单日最大交易次数
            max_per_symbol: 单股票单日最大交易次数
            data_dir: 数据目录 (默认项目 data 目录)
        """
        self.cooldown_seconds = cooldown_seconds
        self.max_daily_orders = max_daily_orders
        self.max_per_symbol = max_per_symbol
        
        # 数据目录 - 默认使用项目 data 目录
        if data_dir is None:
            # 获取项目根目录 (假设在 src/quant_trader/ 下)
            import os
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            data_dir = os.path.join(project_root, "data")
        
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.order_file = self.data_dir / "order_guard.json"
        
        # 内存缓存
        self.orders: list[OrderRecord] = []
        self._load_orders()
    
    def _load_orders(self):
        """从文件加载订单记录"""
        if self.order_file.exists():
            try:
                with open(self.order_file, "r") as f:
                    data = json.load(f)
                    self.orders = [
                        OrderRecord(
                            symbol=o["symbol"],
                            side=o["side"],
                            qty=o["qty"],
                            price=o["price"],
                            timestamp=o["timestamp"],
                            order_id=o.get("order_id", ""),
                            status=o.get("status", "filled"),
                        )
                        for o in data
                    ]
                logger.info(f"✅ 加载了 {len(self.orders)} 条订单记录")
            except Exception as e:
                logger.warning(f"⚠️ 加载订单记录失败: {e}")
                self.orders = []
    
    def _save_orders(self):
        """保存订单记录到文件"""
        try:
            data = [
                {
                    "symbol": o.symbol,
                    "side": o.side,
                    "qty": o.qty,
                    "price": o.price,
                    "timestamp": o.timestamp,
                    "order_id": o.order_id,
                    "status": o.status,
                }
                for o in self.orders
            ]
            with open(self.order_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"❌ 保存订单记录失败: {e}")
    
    def _get_today_orders(self) -> list[OrderRecord]:
        """获取今日订单"""
        today = datetime.now().date()
        return [
            o for o in self.orders
            if datetime.fromtimestamp(o.timestamp).date() == today
            and o.status == "filled"
        ]
    
    def _get_symbol_orders_today(self, symbol: str) -> list[OrderRecord]:
        """获取今日某股票的订单"""
        today = datetime.now().date()
        return [
            o for o in self.orders
            if o.symbol == symbol
            and datetime.fromtimestamp(o.timestamp).date() == today
            and o.status == "filled"
        ]
    
    def _get_last_order(self, symbol: str, side: str) -> Optional[OrderRecord]:
        """获取同股票同方向的最近订单"""
        matching = [
            o for o in self.orders
            if o.symbol == symbol and o.side == side and o.status == "filled"
        ]
        if not matching:
            return None
        return max(matching, key=lambda o: o.timestamp)
    
    def can_order(self, symbol: str, side: str) -> OrderGuardReport:
        """
        检查是否可以下单
        
        Args:
            symbol: 股票代码
            side: BUY 或 SELL
            
        Returns:
            OrderGuardReport: 包含是否允许下单及原因
        """
        now = time.time()
        today_orders = self._get_today_orders()
        symbol_orders = self._get_symbol_orders_today(symbol)
        
        # 检查 1: 单日最大交易次数
        if len(today_orders) >= self.max_daily_orders:
            logger.warning(f"❌ 禁止下单: 今日已交易 {len(today_orders)} 次 (上限 {self.max_daily_orders})")
            return OrderGuardReport(
                allowed=False,
                reason=f"今日已交易 {len(today_orders)} 次，上限 {self.max_daily_orders}",
                today_count=len(today_orders),
            )
        
        # 检查 2: 单股票单日最大交易次数
        if len(symbol_orders) >= self.max_per_symbol:
            logger.warning(f"❌ 禁止下单: {symbol} 今日已交易 {len(symbol_orders)} 次 (上限 {self.max_per_symbol})")
            return OrderGuardReport(
                allowed=False,
                reason=f"{symbol} 今日已交易 {len(symbol_orders)} 次，上限 {self.max_per_symbol}",
                today_count=len(today_orders),
                symbol_count=len(symbol_orders),
            )
        
        # 检查 3: 冷却时间
        last_order = self._get_last_order(symbol, side)
        if last_order:
            elapsed = now - last_order.timestamp
            if elapsed < self.cooldown_seconds:
                remaining = self.cooldown_seconds - elapsed
                logger.warning(f"❌ 禁止下单: {symbol} {side} 冷却中，还需 {remaining:.0f} 秒")
                return OrderGuardReport(
                    allowed=False,
                    reason=f"冷却中，还需 {remaining:.0f} 秒",
                    cooldown_remaining=remaining,
                    today_count=len(today_orders),
                    symbol_count=len(symbol_orders),
                    last_order=last_order,
                )
        
        # 全部通过
        return OrderGuardReport(
            allowed=True,
            reason="可以下单",
            today_count=len(today_orders),
            symbol_count=len(symbol_orders),
            last_order=last_order,
        )
    
    def record_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        order_id: str = "",
    ):
        """
        记录订单
        
        Args:
            symbol: 股票代码
            side: BUY 或 SELL
            qty: 数量
            price: 价格
            order_id: 订单ID
        """
        order = OrderRecord(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            timestamp=time.time(),
            order_id=order_id,
            status="filled",
        )
        
        self.orders.append(order)
        self._save_orders()
        
        logger.info(f"📝 记录订单: {symbol} {side} x {qty} @ {price}")
    
    def get_status(self) -> dict:
        """获取当前防护状态"""
        today_orders = self._get_today_orders()
        
        return {
            "today_orders": len(today_orders),
            "max_daily_orders": self.max_daily_orders,
            "cooldown_seconds": self.cooldown_seconds,
            "remaining_orders": self.max_daily_orders - len(today_orders),
            "recent_orders": [
                {
                    "symbol": o.symbol,
                    "side": o.side,
                    "qty": o.qty,
                    "time": datetime.fromtimestamp(o.timestamp).strftime("%H:%M:%S"),
                }
                for o in sorted(today_orders, key=lambda x: x.timestamp, reverse=True)[:5]
            ],
        }
    
    def reset(self):
        """重置所有记录"""
        self.orders = []
        self._save_orders()
        logger.info("✅ 订单记录已重置")


# 全局实例
_order_guard: Optional[OrderGuard] = None


def get_order_guard(data_dir: str = None) -> OrderGuard:
    """获取全局 OrderGuard 实例"""
    global _order_guard
    if _order_guard is None:
        _order_guard = OrderGuard(data_dir=data_dir)
    return _order_guard
