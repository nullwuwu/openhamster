"""
富途券商

基于富途 OpenD API
"""
import logging
from typing import Optional, List, Dict

from .base_broker import BaseBroker

logger = logging.getLogger("quant_trader.broker.futu")

# 富途 API 导入
try:
    from futu import OpenSecTradeContext
    FUTU_AVAILABLE = True
except ImportError:
    FUTU_AVAILABLE = False
    logger.warning("futu-api 未安装")


class FutuBroker(BaseBroker):
    """富途券商"""
    
    name = "futu"
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 11111,
        trd_env: str = "SIMULATE",  # SIMULATE / REAL
        market: str = "HK",
        security_firm: str = "FUTUSECURITIES",
    ):
        """
        初始化
        
        Args:
            host: OpenD 地址
            port: OpenD 端口
            trd_env: 交易环境 (SIMULATE/REAL)
            market: 市场 (HK/US/CN)
            security_firm: 券商
        """
        if not FUTU_AVAILABLE:
            raise RuntimeError("futu-api 未安装: pip install futu-api")
        
        self.host = host
        self.port = port
        self.trd_env = trd_env
        self.market = market
        self.security_firm = security_firm
        
        self._ctx: Optional[OpenSecTradeContext] = None
        self._connected = False
    
    def connect(self) -> bool:
        """连接富途 OpenD"""
        try:
            # 创建交易上下文
            self._ctx = OpenSecTradeContext(
                filter_trdmarket=self.market,
                host=self.host,
                port=self.port,
                security_firm=self.security_firm,
            )
            
            # 启动连接
            self._ctx.start()
            
            # 设置模拟账户
            if self.trd_env == "SIMULATE":
                sim_acc_id = self._ctx._get_default_acc_id("SIMULATE")
                self._ctx._acc_id = sim_acc_id
                logger.info(f"已设置模拟账户: {sim_acc_id}")
            
            # 等待连接就绪
            import time
            for _ in range(10):
                time.sleep(0.5)
                if self._ctx.status in ['connected', 'READY']:
                    self._connected = True
                    logger.info(f"✅ 富途已连接 (status: {self._ctx.status})")
                    return True
            
            logger.warning(f"⚠️ 富途连接状态: {self._ctx.status}")
            return self._ctx.status == 'READY'
            
        except Exception as e:
            logger.error(f"❌ 富途连接异常: {e}")
            return False
    
    def disconnect(self) -> None:
        """断开连接"""
        if self._ctx:
            self._ctx.stop()
            self._ctx = None
            self._connected = False
            logger.info("🔌 富途连接已关闭")
    
    def get_account(self) -> Dict:
        """获取账户信息"""
        if not self._ctx or not self._connected:
            return {"cash": 0, "total_assets": 0, "positions_value": 0}
        
        try:
            ret, data = self._ctx.accinfo_query()
            if ret == 0 and not data.empty:
                row = data.iloc[0]
                return {
                    "cash": float(row.get("cash", 0) or 0),
                    "total_assets": float(row.get("total_assets", 0) or 0),
                    "positions_value": float(row.get("securities_assets", 0) or 0),
                    "available_cash": float(row.get("avl_withdrawal_cash", 0) or 0),
                }
        except Exception as e:
            logger.error(f"❌ 获取账户失败: {e}")
        
        return {"cash": 0, "total_assets": 0, "positions_value": 0}
    
    def get_positions(self) -> List[Dict]:
        """获取持仓"""
        if not self._ctx or not self._connected:
            return []
        
        try:
            ret, data = self._ctx.position_list_query()
            if ret == 0 and not data.empty:
                positions = []
                for _, row in data.iterrows():
                    positions.append({
                        "symbol": str(row.get("code", "")),
                        "qty": int(row.get("qty", 0)),
                        "avg_cost": float(row.get("cost_price", 0)),
                        "market_value": float(row.get("market_value", 0)),
                    })
                return positions
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
            symbol: 股票代码 (如 2800.HK)
            side: BUY / SELL
            qty: 数量
            price: 价格 (None = 市价)
            
        Returns:
            str: 订单ID
        """
        if not self._ctx or not self._connected:
            raise RuntimeError("未连接富途")
        
        # 转换标的格式
        if not "." in symbol:
            symbol = f"{symbol}.HK"
        
        from futu import TrdSide, OrderType
        
        # 交易方向
        trd_side = TrdSide.BUY if side == "BUY" else TrdSide.SELL
        
        # 订单类型
        order_type = OrderType.MARKET if price is None else OrderType.LIMIT
        
        try:
            ret, data = self._ctx.place_order(
                code=symbol,
                price=price or 0,
                qty=qty,
                trd_side=trd_side,
                order_type=order_type,
            )
            
            if ret == 0:
                order_id = str(data.iloc[0]["order_id"])
                logger.info(f"📝 富途下单成功: {order_id}")
                return order_id
            else:
                raise RuntimeError(f"下单失败: {data}")
                
        except Exception as e:
            logger.error(f"❌ 富途下单异常: {e}")
            raise
    
    def get_order_status(self, order_id: str) -> Dict:
        """获取订单状态"""
        if not self._ctx or not self._connected:
            return {"order_id": order_id, "status": "UNKNOWN", "filled_qty": 0, "avg_price": 0}
        
        try:
            ret, data = self._ctx.order_list_query()
            if ret == 0 and not data.empty:
                for _, row in data.iterrows():
                    if str(row.get("order_id")) == order_id:
                        return {
                            "order_id": str(row.get("order_id")),
                            "status": str(row.get("status", "")),
                            "filled_qty": int(row.get("filled_qty", 0)),
                            "avg_price": float(row.get("avg_price", 0)),
                        }
        except Exception as e:
            logger.error(f"❌ 获取订单状态失败: {e}")
        
        return {"order_id": order_id, "status": "UNKNOWN", "filled_qty": 0, "avg_price": 0}
    
    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        if not self._ctx or not self._connected:
            return False
        
        try:
            ret, data = self._ctx.cancel_order(order_id)
            if ret == 0:
                logger.info(f"✅ 撤单成功: {order_id}")
                return True
        except Exception as e:
            logger.error(f"❌ 撤单失败: {e}")
        
        return False
