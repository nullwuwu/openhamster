"""
Broker 抽象基类

券商接口统一抽象
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict


class BaseBroker(ABC):
    """券商接口抽象基类"""
    
    name: str = "base"
    
    @abstractmethod
    def connect(self) -> bool:
        """连接券商"""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
        pass
    
    @abstractmethod
    def get_account(self) -> Dict:
        """
        获取账户信息
        
        Returns:
            dict: {
                "cash": float,
                "total_assets": float,
                "positions_value": float,
            }
        """
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Dict]:
        """
        获取持仓
        
        Returns:
            list[dict]: [{
                "symbol": str,
                "qty": int,
                "avg_cost": float,
                "market_value": float,
            }]
        """
        pass
    
    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,  # BUY / SELL
        qty: int,
        price: Optional[float] = None,
    ) -> str:
        """
        下单
        
        Args:
            symbol: 股票代码
            side: 买入/卖出
            qty: 数量
            price: 价格 (None = 市价)
            
        Returns:
            str: 订单ID
        """
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict:
        """
        获取订单状态
        
        Returns:
            dict: {
                "order_id": str,
                "status": str,
                "filled_qty": int,
                "avg_price": float,
            }
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        撤单
        
        Returns:
            bool: 是否成功
        """
        pass
