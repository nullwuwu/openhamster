"""
模拟盘账户

管理现金和持仓
"""
from dataclasses import dataclass, field
from typing import Dict, Optional
import logging

from ..strategy.signals import Signal
from ..storage.models import Position

logger = logging.getLogger("quant_trader.paper")


@dataclass
class PaperAccount:
    """模拟盘账户"""
    
    initial_capital: float = 1_000_000  # 初始资金 HKD
    cash: float = 0.0
    positions: Dict[str, dict] = field(default_factory=dict)  # symbol -> {quantity, avg_cost}
    
    def __post_init__(self):
        if self.cash == 0.0:
            self.cash = self.initial_capital
    
    def buy(self, symbol: str, price: float, quantity: int) -> bool:
        """
        买入
        
        Args:
            symbol: 股票代码
            price: 价格
            quantity: 股数
            
        Returns:
            bool: 是否成功
        """
        cost = price * quantity
        
        # 检查现金是否足够
        if cost > self.cash:
            logger.warning(f"现金不足: 需要 {cost:.2f}, 持有 {self.cash:.2f}")
            return False
        
        # 更新现金
        self.cash -= cost
        
        # 更新持仓
        if symbol in self.positions:
            old_qty = self.positions[symbol]["quantity"]
            old_cost = self.positions[symbol]["avg_cost"]
            new_qty = old_qty + quantity
            new_avg_cost = (old_cost * old_cost + price * quantity) / new_qty
            self.positions[symbol] = {
                "quantity": new_qty,
                "avg_cost": new_avg_cost,
            }
        else:
            self.positions[symbol] = {
                "quantity": quantity,
                "avg_cost": price,
            }
        
        logger.info(f"🟢 买入 {symbol} x {quantity} @ {price:.2f}, 成本: {cost:.2f}")
        return True
    
    def sell(self, symbol: str, price: float, quantity: Optional[int] = None) -> bool:
        """
        卖出
        
        Args:
            symbol: 股票代码
            price: 价格
            quantity: 股数 (None 表示全部)
            
        Returns:
            bool: 是否成功
        """
        if symbol not in self.positions:
            logger.warning(f"无持仓: {symbol}")
            return False
        
        position = self.positions[symbol]
        qty = quantity if quantity is not None else position["quantity"]
        
        # 不能卖空
        if qty > position["quantity"]:
            logger.warning(f"持仓不足: 需要 {qty}, 持有 {position['quantity']}")
            qty = position["quantity"]
        
        if qty <= 0:
            return False
        
        # 更新现金
        proceeds = price * qty
        self.cash += proceeds
        
        # 更新持仓
        position["quantity"] -= qty
        if position["quantity"] <= 0:
            del self.positions[symbol]
        
        logger.info(f"🔴 卖出 {symbol} x {qty} @ {price:.2f}, 收入: {proceeds:.2f}")
        return True
    
    def get_position(self, symbol: str) -> Optional[dict]:
        """获取持仓"""
        return self.positions.get(symbol)
    
    def total_equity(self, price_map: Dict[str, float]) -> float:
        """
        计算总权益
        
        Args:
            price_map: symbol -> 最新价格
            
        Returns:
            总权益
        """
        position_value = 0.0
        for symbol, pos in self.positions.items():
            price = price_map.get(symbol, 0)
            position_value += pos["quantity"] * price
        
        return self.cash + position_value
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "cash": self.cash,
            "positions": self.positions,
        }
