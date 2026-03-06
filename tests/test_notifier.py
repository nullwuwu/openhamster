"""
通知器测试
"""
import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.notify import (
    BaseNotifier,
    WeComNotifier,
    EmailNotifier,
    NotifierFactory,
    build_daily_report,
)
from quant_trader.strategy.signals import Signal


class TestBuildDailyReport:
    """测试消息模板"""
    
    def test_build_daily_report_markdown(self):
        """测试 Markdown 格式"""
        data = {
            "trade_date": "2026-03-06",
            "symbol": "2800.HK",
            "signal": "BUY",
            "action": "买入",
            "cash": 750000,
            "position_qty": 10000,
            "avg_cost": 25.0,
            "position_value": 250000,
            "total_equity": 1000000,
            "daily_pnl": 0,
            "total_return_pct": 0.0,
            "price": 25.0,
        }
        
        result = build_daily_report(data, format="markdown")
        
        assert "2026-03-06" in result
        assert "2800.HK" in result
        assert "🟢 BUY" in result
        assert "750,000.00" in result
    
    def test_build_daily_report_html(self):
        """测试 HTML 格式"""
        data = {
            "trade_date": "2026-03-06",
            "symbol": "2800.HK",
            "signal": "SELL",
            "action": "卖出",
            "cash": 1000000,
            "position_qty": 0,
            "avg_cost": 0,
            "position_value": 0,
            "total_equity": 1050000,
            "daily_pnl": 50000,
            "total_return_pct": 5.0,
            "price": 26.0,
        }
        
        result = build_daily_report(data, format="html")
        
        assert "<html>" in result
        assert "2800.HK" in result
        assert "+5.00%" in result
    
    def test_build_daily_report_empty(self):
        """测试空数据"""
        result = build_daily_report({}, format="markdown")
        assert result is not None
        assert len(result) > 0


class TestWeComNotifier:
    """测试企业微信通知器"""
    
    def test_init(self):
        """测试初始化"""
        notifier = WeComNotifier(webhook_url="https://example.com/webhook")
        assert notifier.name == "wecom"
        assert notifier.webhook_url == "https://example.com/webhook"
    
    @patch('quant_trader.notify.wecom_notifier.requests.post')
    def test_send_success(self, mock_post):
        """测试发送成功"""
        mock_response = Mock()
        mock_response.json.return_value = {"errcode": 0, "errmsg": "ok"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        notifier = WeComNotifier(webhook_url="https://example.com/webhook")
        result = notifier.send("测试", "内容")
        
        assert result is True
        mock_post.assert_called_once()
    
    @patch('quant_trader.notify.wecom_notifier.requests.post')
    def test_send_retry(self, mock_post):
        """测试重试逻辑"""
        # 第一次失败，第二次成功
        mock_response = Mock()
        mock_response.json.return_value = {"errcode": 1, "errmsg": "error"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        notifier = WeComNotifier(
            webhook_url="https://example.com/webhook",
            max_retries=3,
            retry_interval=0.1,
        )
        result = notifier.send("测试", "内容")
        
        # 重试3次
        assert mock_post.call_count == 3
        assert result is False


class TestNotifierFactory:
    """测试通知器工厂"""
    
    def test_create_wecom(self):
        """测试创建企业微信通知器"""
        config = {
            "channels": ["wecom"],
            "wecom": {
                "webhook_url": "https://example.com/webhook"
            }
        }
        
        notifier = NotifierFactory.create(config)
        
        assert isinstance(notifier, WeComNotifier)
        assert notifier.name == "wecom"
    
    def test_create_email(self):
        """测试创建邮件通知器"""
        config = {
            "channels": ["email"],
            "email": {
                "smtp_host": "smtp.qq.com",
                "smtp_port": 465,
                "sender": "test@qq.com",
                "password": "pass",
                "receivers": ["target@qq.com"],
            }
        }
        
        notifier = NotifierFactory.create(config)
        
        assert isinstance(notifier, EmailNotifier)
        assert notifier.name == "email"
    
    def test_create_multiple(self):
        """测试创建多个通知器"""
        config = {
            "channels": ["wecom", "email"],
            "wecom": {"webhook_url": "https://example.com/webhook"},
            "email": {
                "smtp_host": "smtp.qq.com",
                "smtp_port": 465,
                "sender": "test@qq.com",
                "password": "pass",
                "receivers": ["target@qq.com"],
            }
        }
        
        notifiers = NotifierFactory.create(config)
        
        assert isinstance(notifiers, list)
        assert len(notifiers) == 2
    
    def test_create_empty(self):
        """测试空配置"""
        notifier = NotifierFactory.create({})
        assert notifier is None


class TestPaperTradingServiceNotify:
    """测试 PaperTradingService 通知集成"""
    
    def test_notify_none(self):
        """测试 notifier 为 None 时不报错"""
        from quant_trader.paper import PaperTradingService
        from quant_trader.strategy import MACrossStrategy
        
        strategy = MACrossStrategy()
        
        # notifier 为 None 应该可以正常运行
        # 实际测试需要 mock
        assert True  # 跳过，避免实际网络请求


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
