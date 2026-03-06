"""
Longbridge 券商

基于长桥 API
"""
import logging
import os
from typing import Optional, List, Dict

from .base_broker import BaseBroker

logger = logging.getLogger("quant_trader.broker.longbridge")


class LongbridgeBroker(BaseBroker):
    """长桥券商"""
    
    name = "longbridge"
    
    def __init__(
        self,
        mode: str = "readonly",  # readonly / dry_run / live
        max_order_value: float = 5000,
        require_confirm_live: bool = True,
    ):
        """
        初始化
        
        Args:
            mode: 模式 (readonly/dry_run/live)
            max_order_value: 单笔最大下单金额
            require_confirm_live: live 模式启动时是否需要确认
        """
        self.mode = mode
        self.max_order_value = max_order_value
        self.require_confirm_live = require_confirm_live
        
        self._client = None
        self._connected = False
    
    def connect(self) -> bool:
        """连接长桥"""
        try:
            from longport import openapi
            
            # 使用 from_env() 自动从环境变量加载配置
            # 支持 LONGPORT_APP_KEY, LONGPORT_APP_SECRET, LONGPORT_ACCESS_TOKEN
            config = openapi.Config.from_env()
            
            # 创建客户端
            self._client = openapi.TradeContext(config)
            
            # 测试连接 - 获取账户资金
            self._client.account_balance()
            
            self._connected = True
            logger.info(f"✅ 长桥已连接 (mode: {self.mode})")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 长桥连接失败: {e}")
            return False
    
    def disconnect(self) -> None:
        """断开连接"""
        self._client = None
        self._connected = False
        logger.info("🔌 长桥连接已关闭")
    
    def get_account(self) -> Dict:
        """获取账户信息"""
        if not self._client or not self._connected:
            return {"cash": 0, "total_assets": 0, "positions_value": 0}
        
        try:
            bal_list = self._client.account_balance()
            bal = bal_list[0]  # 返回是列表
            
            cash_info = bal.cash_infos[0] if bal.cash_infos else None
            
            return {
                "cash": float(cash_info.available_cash) if cash_info else 0,
                "total_assets": float(bal.total_cash),
                "positions_value": float(bal.net_assets - cash_info.available_cash) if cash_info else 0,
            }
            
        except Exception as e:
            logger.error(f"❌ 获取账户失败: {e}")
            return {"cash": 0, "total_assets": 0, "positions_value": 0}
    
    def get_positions(self) -> List[Dict]:
        """获取持仓"""
        if not self._client or not self._connected:
            return []
        
        try:
            resp = self._client.stock_positions()
            
            result = []
            for ch in resp.channels:
                for p in ch.positions:
                    result.append({
                        "symbol": p.symbol,
                        "qty": p.quantity,
                        "avg_cost": float(p.cost_bar),
                        "market_value": float(p.market_value) if p.market_value else 0,
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 获取持仓失败: {e}")
            return []
    
    def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: Optional[float] = None,
    ) -> str:
        """
        下单
        
        Args:
            symbol: 股票代码
            side: BUY / SELL
            qty: 数量
            price: 价格 (None = 市价)
            
        Returns:
            str: 订单ID
        """
        # 检查模式
        if self.mode == "readonly":
            raise PermissionError("Broker is in readonly mode")
        
        # 计算订单金额
        order_value = qty * (price or 0)
        
        if self.mode == "dry_run":
            logger.info(f"[DRY_RUN] Would place order: {side} {qty} {symbol} @ {price or 'market'}")
            return f"DRY_RUN_{symbol}"
        
        # live 模式
        if not self._client or not self._connected:
            raise RuntimeError("未连接长桥")
        
        # 检查最大下单金额
        if order_value > self.max_order_value:
            raise ValueError(f"订单金额 {order_value} 超过上限 {self.max_order_value}")
        
        try:
            from longport import openapi
            
            # 构建订单
            order_type = openapi.OrderType.LIMIT if price else openapi.OrderType.MARKET
            order_side = openapi.OrderSide.BUY if side == "BUY" else openapi.OrderSide.SELL
            
            # 下单
            result = self._client.submit_order(
                symbol=symbol,
                order_type=order_type,
                order_side=order_side,
                time_in_force=openapi.TimeInForceType.DAY,
                quantity=qty,
                price=price,
            )
            
            order_id = str(result.order_id)
            logger.info(f"📝 长桥下单成功: {order_id}")
            return order_id
            
        except Exception as e:
            logger.error(f"❌ 长桥下单失败: {e}")
            raise
    
    def get_order_status(self, order_id: str) -> Dict:
        """获取订单状态"""
        if not self._client or not self._connected:
            return {"order_id": order_id, "status": "UNKNOWN", "filled_qty": 0, "avg_price": 0}
        
        try:
            orders = self._client.today_orders()
            
            for order in orders:
                if str(order.order_id) == order_id:
                    return {
                        "order_id": str(order.order_id),
                        "status": order.status.name,
                        "filled_qty": order.filled_quantity,
                        "avg_price": float(order.avg_price) if order.avg_price else 0,
                    }
            
        except Exception as e:
            logger.error(f"❌ 获取订单状态失败: {e}")
        
        return {"order_id": order_id, "status": "UNKNOWN", "filled_qty": 0, "avg_price": 0}
    
    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        if not self._client or not self._connected:
            return False
        
        if self.mode == "readonly":
            raise PermissionError("Broker is in readonly mode")
        
        if self.mode == "dry_run":
            logger.info(f"[DRY_RUN] Would cancel order: {order_id}")
            return True
        
        try:
            self._client.cancel_order(order_id)
            logger.info(f"✅ 撤单成功: {order_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 撤单失败: {e}")
            return False
