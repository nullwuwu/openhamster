"""
通知器抽象基类
"""
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger("quant_trader.notify")


class BaseNotifier(ABC):
    """通知器抽象基类"""
    
    name: str = "base"
    
    def __init__(self):
        pass
    
    @abstractmethod
    def send(self, title: str, body: str) -> bool:
        """
        发送通知
        
        Args:
            title: 标题
            body: 内容
            
        Returns:
            bool: 是否成功
        """
        pass
    
    def format_message(self, data: dict) -> str:
        """
        格式化消息（默认实现）
        
        Args:
            data: 数据字典
            
        Returns:
            str: 格式化后的消息
        """
        lines = []
        for key, value in data.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)
