"""
通知模块

支持企业微信、邮件等多种推送渠道
"""
from .base_notifier import BaseNotifier
from .wecom_notifier import WeComNotifier
from .email_notifier import EmailNotifier
from .notifier_factory import NotifierFactory
from .templates import build_daily_report, build_alert_message

__all__ = [
    "BaseNotifier",
    "WeComNotifier",
    "EmailNotifier",
    "NotifierFactory",
    "build_daily_report",
    "build_alert_message",
]
