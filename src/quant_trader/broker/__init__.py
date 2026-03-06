"""
券商模块

支持多种券商接口
"""
from .base_broker import BaseBroker
from .paper_broker import PaperBroker
from .futu_broker import FutuBroker
from .longbridge_broker import LongbridgeBroker
from .order_state import OrderStateMachine, OrderState
from .reconciler import Reconciler

__all__ = [
    "BaseBroker",
    "PaperBroker",
    "FutuBroker",
    "LongbridgeBroker",
    "OrderStateMachine",
    "OrderState",
    "Reconciler",
]


def create_broker(config: dict) -> BaseBroker:
    """
    根据配置创建券商
    
    Args:
        config: 配置字典
            {
                "type": "paper" | "futu" | "longbridge",
                ... // 其他参数
            }
            
    Returns:
        BaseBroker 实例
    """
    broker_type = config.get("type", "paper")
    
    if broker_type == "paper":
        return PaperBroker(
            initial_capital=config.get("initial_capital", 1_000_000)
        )
    
    elif broker_type == "futu":
        return FutuBroker(
            host=config.get("host", "127.0.0.1"),
            port=config.get("port", 11111),
            trd_env=config.get("trd_env", "SIMULATE"),
            market=config.get("market", "HK"),
            security_firm=config.get("security_firm", "FUTUSECURITIES"),
        )
    
    elif broker_type == "longbridge":
        return LongbridgeBroker(
            mode=config.get("mode", "readonly"),
            max_order_value=config.get("max_order_value", 5000),
            require_confirm_live=config.get("require_confirm_live", True),
        )
    
    else:
        raise ValueError(f"Unknown broker type: {broker_type}")
