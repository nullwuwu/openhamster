"""
本地模拟券商

继承原有 PaperAccount 逻辑
"""
import logging
from typing import Optional, List, Dict

from .base_broker import BaseBroker

logger = logging.getLogger("quant_trader.broker")


class PaperBroker(BaseBroker):
    """本地模拟券商"""
    
    name = "paper"
    
    def __init__(self, initial_capital: float = 1_000_000):
        """
        初始化
        
        Args:
            initial_capital: 初始资金
        """
        self.initial_capital = initial_capital
        self._cash = initial_capital
        self._positions: Dict[str, dict] = {}
        self._orders: Dict[str, dict] = {}
        self._order_counter = 0
    
    def connect(self) -> bool:
        """连接（本地模拟无需连接）"""
        logger.info("📄 PaperBroker 初始化")
        return True
    
    def disconnect(self) -> None:
        """断开连接"""
        pass
    
    def get_account(self) -> Dict:
        """获取账户信息"""
        positions_value = sum(
            pos["market_value"] for pos in self._positions.values()
        )
        
        return {
            "cash": self._cash,
            "total_assets": self._cash + positions_value,
            "positions_value": positions_value,
        }
    
    def get_positions(self) -> List[Dict]:
        """获取持仓"""
        return [
            {
                "symbol": symbol,
                "qty": pos["qty"],
                "avg_cost": pos["avg_cost"],
                "market_value": pos["market_value"],
            }
            for symbol, pos in self._positions.items()
            if pos["qty"] > 0
        ]
    
    def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: Optional[float] = None,
    ) -> str:
        """
        下单（模拟即时成交）
        """
        self._order_counter += 1
        order_id = f"PAPER_{self._order_counter}"
        
        if price is None:
            # 市价单，使用模拟价格
            price = 0
        
        order = {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "filled_qty": qty,
            "avg_price": price,
            "status": "FILLED_ALL",
        }
        
        self._orders[order_id] = order
        
        # 执行成交
        if side == "BUY":
            cost = qty * price
            if self._cash >= cost:
                self._cash -= cost
                
                if symbol in self._positions:
                    old = self._positions[symbol]
                    new_qty = old["qty"] + qty
                    new_cost = old["avg_cost"] * old["qty"] + price * qty
                    self._positions[symbol] = {
                        "qty": new_qty,
                        "avg_cost": new_cost / new_qty,
                        "market_value": new_qty * price,
                    }
                else:
                    self._positions[symbol] = {
                        "qty": qty,
                        "avg_cost": price,
                        "market_value": qty * price,
                    }
                
                logger.info(f"🟢 模拟买入 {symbol} x {qty} @ {price}")
        
        elif side == "SELL":
            if symbol in self._positions and self._positions[symbol]["qty"] >= qty:
                proceeds = qty * price
                self._cash += proceeds
                
                pos = self._positions[symbol]
                pos["qty"] -= qty
                if pos["qty"] == 0:
                    del self._positions[symbol]
                else:
                    pos["market_value"] = pos["qty"] * price
                
                logger.info(f"🔴 模拟卖出 {symbol} x {qty} @ {price}")
        
        return order_id
    
    def get_order_status(self, order_id: str) -> Dict:
        """获取订单状态"""
        if order_id in self._orders:
            return self._orders[order_id]
        
        return {
            "order_id": order_id,
            "status": "UNKNOWN",
            "filled_qty": 0,
            "avg_price": 0,
        }
    
    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        if order_id in self._orders:
            self._orders[order_id]["status"] = "CANCELLED"
            return True
        return False
    
    def reset(self):
        """重置（用于测试）"""
        self._cash = self.initial_capital
        self._positions = {}
        self._orders = {}
        self._order_counter = 0
