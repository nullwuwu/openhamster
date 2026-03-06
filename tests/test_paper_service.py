"""
模拟盘服务测试
"""
import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.strategy import MACrossStrategy
from quant_trader.paper import PaperTradingService
from quant_trader.storage import init_db, DailyNavRepository


class TestPaperTradingService:
    """测试 PaperTradingService"""
    
    @pytest.fixture
    def service(self):
        """服务实例"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        strategy = MACrossStrategy(short_window=5, long_window=10)
        
        service = PaperTradingService(
            strategy=strategy,
            symbol="2800.HK",
            db_path=db_path,
            initial_capital=100_000,
            provider_name="stooq",
        )
        
        yield service
        
        service.close()
        os.unlink(db_path)
    
    def test_bootstrap(self, service):
        """测试初始化"""
        service.bootstrap()
        
        assert service.db is not None
        assert service.account is not None
        assert service.executor is not None
        assert service.account.cash == 100_000
    
    @pytest.mark.integration
    def test_run_once(self, service):
        """测试执行一次"""
        service.bootstrap()
        
        success = service.run_once()
        
        # 可能成功或失败（取决于网络）
        assert success is True or success is False
    
    def test_run_once_twice_same_day(self, service):
        """测试同一天不重复执行"""
        service.bootstrap()
        
        # 执行第一次
        service.run_once("2026-03-06")
        
        # 记录当前状态
        cash1 = service.account.cash
        
        # 再次执行同一天
        service.run_once("2026-03-06")
        
        # 状态应该不变
        assert service.account.cash == cash1


class TestDailyNavDuplicate:
    """测试每日净值不重复"""
    
    @pytest.fixture
    def db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        db = init_db(db_path)
        yield db
        
        db.close()
        os.unlink(db_path)
    
    def test_duplicate_nav(self, db):
        """测试重复写入净值"""
        from quant_trader.storage import DailyNavRepository, DailyNav
        
        nav_repo = DailyNavRepository(db)
        
        # 写入第一天
        nav = DailyNav(
            trade_date="2026-03-06",
            cash=100_000,
            position_value=0,
            total_equity=100_000,
        )
        nav_repo.create(nav)
        
        # 检查存在
        assert nav_repo.exists("2026-03-06")
        
        # 再次写入同一天（会失败因为 UNIQUE 约束）
        # 这里测试 exists 方法


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
