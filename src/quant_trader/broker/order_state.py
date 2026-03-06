"""
订单状态机

处理订单生命周期
"""
import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger("quant_trader.broker")

# 订单状态
class OrderState(Enum):
    PENDING = "PENDING"       # 待提交
    SUBMITTED = "SUBMITTED"   # 已提交
    FILLED_PART = "FILLED_PART"   # 部分成交
    FILLED_ALL = "FILLED_ALL"     # 全部成交
    CANCELLED = "CANCELLED"   # 已取消
    FAILED = "FAILED"         # 失败

# 终态
FINAL_STATES = {OrderState.FILLED_ALL, OrderState.CANCELLED, OrderState.FAILED}


class OrderStateMachine:
    """订单状态机"""
    
    def __init__(
        self,
        broker,
        max_wait: int = 60,
        poll_interval: int = 2,
    ):
        """
        初始化
        
        Args:
            broker: Broker 实例
            max_wait: 最大等待秒数
            poll_interval: 轮询间隔秒数
        """
        self.broker = broker
        self.max_wait = max_wait
        self.poll_interval = poll_interval
    
    def wait_for_final(
        self,
        order_id: str,
        on_state_change=None,
    ) -> str:
        """
        等待订单到达终态
        
        Args:
            order_id: 订单ID
            on_state_change: 状态变更回调 (optional)
            
        Returns:
            str: 最终状态
        """
        start_time = time.time()
        last_state = None
        
        while time.time() - start_time < self.max_wait:
            # 获取订单状态
            status = self.broker.get_order_status(order_id)
            
            # 解析状态
            state = self._parse_state(status.get("status", ""))
            
            # 状态变更回调
            if state != last_state and on_state_change:
                on_state_change(state, status)
            last_state = state
            
            # 检查终态
            if state in FINAL_STATES:
                logger.info(f"✅ 订单终态: {order_id} -> {state.value}")
                return state.value
            
            # 等待
            time.sleep(self.poll_interval)
        
        # 超时，尝试撤单
        logger.warning(f"⏰ 订单超时未完成: {order_id}，尝试撤单")
        
        if self.broker.cancel_order(order_id):
            return OrderState.CANCELLED.value
        
        return OrderState.FAILED.value
    
    def _parse_state(self, status: str) -> OrderState:
        """解析富途状态"""
        status = status.upper()
        
        if status in ["SUBMITTED", "NOT_TRADED"]:
            return OrderState.SUBMITTED
        elif status in ["FILLED_PART", "PART_FILLED"]:
            return OrderState.FILLED_PART
        elif status in ["FILLED_ALL", "FILLED"]:
            return OrderState.FILLED_ALL
        elif status in ["CANCELLED", "CANCEL"]:
            return OrderState.CANCELLED
        elif status in ["FAILED", "REJECTED"]:
            return OrderState.FAILED
        else:
            return OrderState.PENDING
