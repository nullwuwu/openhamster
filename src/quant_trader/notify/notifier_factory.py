"""
通知器工厂

根据配置创建合适的通知器
"""
import logging
from typing import List, Optional, Union

from .base_notifier import BaseNotifier
from .wecom_notifier import WeComNotifier
from .email_notifier import EmailNotifier

logger = logging.getLogger("quant_trader.notify.factory")


class NotifierFactory:
    """通知器工厂"""
    
    @staticmethod
    def create(config: dict) -> Optional[Union[BaseNotifier, List[BaseNotifier]]]:
        """
        创建通知器
        
        Args:
            config: 配置字典
                {
                    "channels": ["wecom"],  # 或 ["email"], ["wecom", "email"]
                    "wecom": {"webhook_url": "..."},
                    "email": {
                        "smtp_host": "...",
                        "smtp_port": 465,
                        "sender": "...",
                        "password": "...",
                        "receivers": ["..."],
                    }
                }
                
        Returns:
            单个 notifier, notifier 列表, 或 None
        """
        channels = config.get("channels", [])
        
        if not channels:
            logger.info("未配置通知渠道")
            return None
        
        notifiers = []
        
        for channel in channels:
            if channel == "wecom":
                wecom_config = config.get("wecom", {})
                webhook_url = wecom_config.get("webhook_url")
                
                if webhook_url:
                    notifiers.append(WeComNotifier(webhook_url=webhook_url))
                    logger.info("✅ 企业微信通知器已创建")
                else:
                    logger.warning("⚠️ 未配置企业微信 webhook_url")
            
            elif channel == "email":
                email_config = config.get("email", {})
                smtp_host = email_config.get("smtp_host")
                
                if smtp_host:
                    notifier = EmailNotifier(
                        smtp_host=email_config["smtp_host"],
                        smtp_port=email_config.get("smtp_port", 465),
                        sender=email_config["sender"],
                        password=email_config["password"],
                        receivers=email_config.get("receivers", []),
                        use_ssl=email_config.get("use_ssl", True),
                    )
                    notifiers.append(notifier)
                    logger.info("✅ 邮件通知器已创建")
                else:
                    logger.warning("⚠️ 未配置邮件 smtp_host")
        
        if not notifiers:
            return None
        
        # 返回单个或列表
        if len(notifiers) == 1:
            return notifiers[0]
        
        return notifiers
