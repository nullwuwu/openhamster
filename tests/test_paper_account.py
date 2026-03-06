"""
模拟盘账户测试
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.paper import PaperAccount


class TestPaperAccount:
    """测试 PaperAccount"""
    
    def test_init(self):
        """测试初始化"""
        account = PaperAccount(initial_capital=100_000)
        assert account.initial_capital == 100_000
        assert account.cash == 100_000
        assert account.positions == {}
    
    def test_buy(self):
        """测试买入"""
        account = PaperAccount(initial_capital=100_000)
        
        # 买入
        success = account.buy("2800.HK", 25.0, 1000)
        
        assert success
        assert account.cash == 75_000  # 100000 - 25000
        assert "2800.HK" in account.positions
        assert account.positions["2800.HK"]["quantity"] == 1000
        assert account.positions["2800.HK"]["avg_cost"] == 25.0
    
    def test_buy_insufficient_cash(self):
        """测试现金不足"""
        account = PaperAccount(initial_capital=10_000)
        
        # 尝试买入超过现金的股数
        success = account.buy("2800.HK", 25.0, 1000)  # 需要 25000
        
        assert not success
        assert account.cash == 10_000
        assert "2800.HK" not in account.positions
    
    def test_sell(self):
        """测试卖出"""
        account = PaperAccount(initial_capital=100_000)
        
        # 先买入
        account.buy("2800.HK", 25.0, 1000)
        
        # 卖出
        success = account.sell("2800.HK", 26.0)
        
        assert success
        assert "2800.HK" not in account.positions  # 全部卖出
        assert account.cash == 75_000 + 26_000  # 剩余现金 + 卖出收入
    
    def test_sell_partial(self):
        """测试部分卖出"""
        account = PaperAccount(initial_capital=100_000)
        
        # 先买入
        account.buy("2800.HK", 25.0, 1000)
        
        # 部分卖出
        success = account.sell("2800.HK", 26.0, 500)
        
        assert success
        assert account.positions["2800.HK"]["quantity"] == 500
        assert account.cash == 75_000 + 13_000
    
    def test_total_equity(self):
        """测试总权益计算"""
        account = PaperAccount(initial_capital=100_000)
        
        # 买入
        account.buy("2800.HK", 25.0, 1000)
        
        # 计算权益
        equity = account.total_equity({"2800.HK": 26.0})
        
        # 现金 75000 + 持仓 26000 = 101000
        assert equity == 101_000
    
    def test_to_dict(self):
        """测试转换为字典"""
        account = PaperAccount(initial_capital=100_000)
        account.buy("2800.HK", 25.0, 1000)
        
        d = account.to_dict()
        
        assert "cash" in d
        assert "positions" in d
        assert d["positions"]["2800.HK"]["quantity"] == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
