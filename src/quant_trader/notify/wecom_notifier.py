"""
企业微信 Webhook 通知器
"""
import logging
import time
from typing import Optional

import requests

from .base_notifier import BaseNotifier

logger = logging.getLogger("quant_trader.notify.wecom")


class WeComNotifier(BaseNotifier):
    """企业微信 Webhook 通知器"""
    
    name = "wecom"
    
    def __init__(
        self,
        webhook_url: str,
        max_retries: int = 3,
        retry_interval: float = 2.0,
    ):
        """
        初始化
        
        Args:
            webhook_url: Webhook URL
            max_retries: 最大重试次数
            retry_interval: 重试间隔（秒）
        """
        super().__init__()
        self.webhook_url = webhook_url
        self.max_retries = max_retries
        self.retry_interval = retry_interval
    
    def send(self, title: str, body: str) -> bool:
        """
        发送企业微信消息
        
        Args:
            title: 标题
            body: 内容
            
        Returns:
            bool: 是否成功
        """
        # 组合消息
        content = f"**{title}**\n\n{body}"
        
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": content,
            }
        }
        
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10,
                )
                response.raise_for_status()
                
                result = response.json()
                
                if result.get("errcode") == 0:
                    logger.info(f"✅ 企业微信消息发送成功")
                    return True
                else:
                    last_error = result.get("errmsg", "Unknown error")
                    logger.warning(f"⚠️ 企业微信 API 错误: {last_error}")
                    
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                logger.warning(f"⚠️ 企业微信发送失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
            
            # 重试等待
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_interval)
        
        logger.error(f"❌ 企业微信消息发送失败: {last_error}")
        return False
