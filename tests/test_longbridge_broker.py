"""
Longbridge Broker 测试
"""
import pytest
import sys
import os

# 添加路径
sys.path.insert(0, '/Users/a1/.openclaw/workspace/projects/quant-trader/src')

# 设置环境变量
os.environ["LONGBRIDGE_APP_KEY"] = "test_key"
os.environ["LONGBRIDGE_APP_SECRET"] = "test_secret"
os.environ["LONGBRIDGE_ACCESS_TOKEN"] = "test_token"


class TestLongbridgeBroker:
    """测试 LongbridgeBroker 三档模式"""
    
    def test_readonly_mode_place_order(self):
        """readonly 模式不能下单"""
        from quant_trader.broker.longbridge_broker import LongbridgeBroker
        
        broker = LongbridgeBroker(mode="readonly")
        
        with pytest.raises(PermissionError, match="readonly mode"):
            broker.place_order("2800.HK", "BUY", 100, 25.0)
    
    def test_dry_run_mode_place_order(self):
        """dry_run 模式只记日志不实际下单"""
        from quant_trader.broker.longbridge_broker import LongbridgeBroker
        
        broker = LongbridgeBroker(mode="dry_run")
        broker._connected = True
        broker._client = "mock"
        
        # 不需要实际调用 SDK
        order_id = broker.place_order("2800.HK", "BUY", 100, 25.0)
        
        # 应该返回模拟订单ID
        assert "DRY_RUN" in order_id
    
    def test_live_mode_max_value_check(self):
        """live 模式检查最大订单金额"""
        from quant_trader.broker.longbridge_broker import LongbridgeBroker
        
        broker = LongbridgeBroker(mode="live", max_order_value=1000)
        broker._connected = True
        broker._client = "mock"  # 模拟已连接
        
        # 尝试下大单 (100 * 25 = 2500 > 1000)
        with pytest.raises(ValueError, match="超过上限"):
            broker.place_order("2800.HK", "BUY", 100, 25.0)
    
    def test_require_confirm_live_attribute(self):
        """require_confirm_live 属性"""
        from quant_trader.broker.longbridge_broker import LongbridgeBroker
        
        broker = LongbridgeBroker(
            mode="live",
            require_confirm_live=True,
        )
        
        assert broker.mode == "live"
        assert broker.require_confirm_live == True


class TestBrokerFactory:
    """测试工厂函数"""
    
    def test_create_longbridge(self):
        """创建 Longbridge Broker"""
        from quant_trader.broker import create_broker
        
        broker = create_broker({
            "type": "longbridge",
            "mode": "dry_run",
        })
        
        from quant_trader.broker import LongbridgeBroker
        assert isinstance(broker, LongbridgeBroker)
        assert broker.mode == "dry_run"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
