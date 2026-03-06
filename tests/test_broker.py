"""
券商模块测试
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.broker import (
    BaseBroker,
    PaperBroker,
    create_broker,
    OrderStateMachine,
    Reconciler,
)
from quant_trader.strategy.signals import Signal


class TestPaperBroker:
    """测试 PaperBroker"""
    
    def test_create(self):
        """测试创建"""
        broker = create_broker({"type": "paper", "initial_capital": 100000})
        assert broker.name == "paper"
        assert broker.initial_capital == 100000
    
    def test_connect(self):
        """测试连接"""
        broker = PaperBroker(initial_capital=100000)
        assert broker.connect() is True
    
    def test_get_account(self):
        """测试获取账户"""
        broker = PaperBroker(initial_capital=100000)
        broker.connect()
        
        acc = broker.get_account()
        assert acc["cash"] == 100000
        assert acc["total_assets"] == 100000
    
    def test_place_order_buy(self):
        """测试买入"""
        broker = PaperBroker(initial_capital=100000)
        broker.connect()
        
        order_id = broker.place_order("2800.HK", "BUY", 1000, 25.0)
        
        assert order_id.startswith("PAPER_")
        
        # 验证持仓
        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "2800.HK"
        assert positions[0]["qty"] == 1000
        
        # 验证现金
        acc = broker.get_account()
        assert acc["cash"] < 100000
    
    def test_place_order_sell(self):
        """测试卖出"""
        broker = PaperBroker(initial_capital=100000)
        broker.connect()
        
        # 先买入
        broker.place_order("2800.HK", "BUY", 1000, 25.0)
        
        # 卖出
        order_id = broker.place_order("2800.HK", "SELL", 500, 26.0)
        
        # 验证持仓
        positions = broker.get_positions()
        assert positions[0]["qty"] == 500


class TestOrderStateMachine:
    """测试订单状态机"""
    
    def test_order_state_parse(self):
        """测试状态解析"""
        class MockBroker:
            def get_order_status(self, order_id):
                return {"status": "FILLED_ALL", "filled_qty": 100, "avg_price": 25.0}
            
            def cancel_order(self, order_id):
                return True
        
        broker = MockBroker()
        machine = OrderStateMachine(broker, max_wait=1, poll_interval=1)
        
        # 快速返回（因为已经是终态）
        state = machine._parse_state("FILLED_ALL")
        assert state.value == "FILLED_ALL"


class TestReconciler:
    """测试对账器"""
    
    def test_reconcile_match(self):
        """测试匹配"""
        from quant_trader.storage import Database
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        db = Database(db_path)
        reconciler = Reconciler(db)
        
        broker_positions = [
            {"symbol": "2800.HK", "qty": 1000},
        ]
        local_positions = [
            {"symbol": "2800.HK", "qty": 1000},
        ]
        
        result = reconciler.run(broker_positions, local_positions)
        
        assert result["status"] == "MATCH"
        assert result["differences"] == 0
        
        db.close()
        os.unlink(db_path)
    
    def test_reconcile_mismatch(self):
        """测试不匹配"""
        from quant_trader.storage import Database
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        db = Database(db_path)
        reconciler = Reconciler(db)
        
        broker_positions = [
            {"symbol": "2800.HK", "qty": 1000},
        ]
        local_positions = [
            {"symbol": "2800.HK", "qty": 800},
        ]
        
        result = reconciler.run(broker_positions, local_positions)
        
        assert result["status"] == "MISMATCH"
        assert result["differences"] == 1
        assert result["details"][0]["diff"] == 200
        
        db.close()
        os.unlink(db_path)


class TestBackwardCompatibility:
    """测试向后兼容"""
    
    def test_broker_none(self):
        """测试 broker=None 正常工作"""
        from quant_trader.paper import PaperTradingService
        from quant_trader.strategy import MACrossStrategy
        
        strategy = MACrossStrategy()
        
        # 不传 broker，应该能正常工作
        service = PaperTradingService(
            strategy=strategy,
            symbol="2800.HK",
            db_path=":memory:",
            provider_name="stooq",
        )
        
        # bootstrap 应该不报错
        # 注意：需要 mock 数据源
        assert service is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
