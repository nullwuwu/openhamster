"""
风控和优化测试
"""
import pytest
import sys
import os
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.risk import RiskManager
from quant_trader.strategy.signals import Signal


class TestRiskManager:
    """测试风控管理器"""
    
    def test_init(self):
        """测试初始化"""
        rm = RiskManager(
            max_position_pct=0.6,
            stop_loss_pct=0.08,
            take_profit_pct=0.20,
            max_drawdown_pct=0.15,
        )
        
        assert rm.max_position_pct == 0.6
        assert rm.stop_loss_pct == 0.08
        assert rm.take_profit_pct == 0.20
        assert rm.max_drawdown_pct == 0.15
    
    def test_stop_loss_trigger(self):
        """测试止损触发"""
        rm = RiskManager(stop_loss_pct=0.08)
        
        # 持仓亏损超过 8%
        context = {
            "position_qty": 1000,
            "avg_cost": 100.0,
            "current_price": 90.0,  # 亏损 10%
            "total_equity": 100000,
            "cash": 10000,
            "max_drawdown_pct": 0,
        }
        
        signal = Signal.SELL  # 原始信号
        result = rm.evaluate(signal, context)
        
        assert result == Signal.SELL  # 强制卖出
    
    def test_take_profit_trigger(self):
        """测试止盈触发"""
        rm = RiskManager(take_profit_pct=0.20)
        
        context = {
            "position_qty": 1000,
            "avg_cost": 100.0,
            "current_price": 125.0,  # 盈利 25%
            "total_equity": 100000,
            "cash": 10000,
            "max_drawdown_pct": 0,
        }
        
        signal = Signal.HOLD
        result = rm.evaluate(signal, context)
        
        assert result == Signal.SELL  # 强制卖出
    
    def test_max_drawdown_trigger(self):
        """测试回撤超限"""
        rm = RiskManager(max_drawdown_pct=0.15)
        
        context = {
            "position_qty": 0,
            "avg_cost": 0,
            "current_price": 0,
            "total_equity": 85000,
            "cash": 85000,
            "max_drawdown_pct": -0.16,  # 超过 15%
        }
        
        signal = Signal.BUY
        result = rm.evaluate(signal, context)
        
        assert result == Signal.HOLD  # 买入改为 HOLD
    
    def test_position_limit(self):
        """测试仓位超限"""
        rm = RiskManager(max_position_pct=0.6)
        
        context = {
            "position_qty": 0,
            "avg_cost": 0,
            "current_price": 100.0,
            "total_equity": 100000,
            "cash": 100000,  # 全部现金
            "max_drawdown_pct": 0,
        }
        
        # 买入后仓位会超过 60%
        signal = Signal.BUY
        result = rm.evaluate(signal, context)
        
        assert result == Signal.HOLD  # 限制买入
    
    def test_existing_position_no_buy(self):
        """测试已有持仓不允许买入"""
        rm = RiskManager()
        
        context = {
            "position_qty": 1000,
            "avg_cost": 25.0,
            "current_price": 26.0,
            "total_equity": 100000,
            "cash": 74000,
            "max_drawdown_pct": 0,
        }
        
        signal = Signal.BUY
        result = rm.evaluate(signal, context)
        
        assert result == Signal.HOLD  # 不允许重复买入
    
    def test_pass_through(self):
        """测试正常透传"""
        rm = RiskManager()
        
        context = {
            "position_qty": 0,
            "avg_cost": 0,
            "current_price": 0,
            "total_equity": 100000,
            "cash": 100000,
            "max_drawdown_pct": 0,
        }
        
        # 无持仓时 BUY 透传
        result = rm.evaluate(Signal.BUY, context)
        assert result == Signal.BUY
        
        # 无持仓时 SELL 透传
        result = rm.evaluate(Signal.SELL, context)
        assert result == Signal.SELL


class TestGridSearch:
    """测试网格搜索"""
    
    @pytest.mark.integration
    def test_grid_search(self):
        """测试网格搜索"""
        from quant_trader.backtest import GridSearchOptimizer
        
        optimizer = GridSearchOptimizer(
            symbol="2800.HK",
            start_date="2024-01-01",
            end_date="2025-01-01",
            provider_name="stooq",
        )
        
        # 缩小搜索范围加快测试
        df = optimizer.search(
            short_range=[5, 10],
            long_range=[20, 30],
            top_n=3,
        )
        
        assert not df.empty
        assert "sharpe_ratio" in df.columns
        
        # 检查排序
        if len(df) > 1:
            assert df.iloc[0]["sharpe_ratio"] >= df.iloc[1]["sharpe_ratio"]
        
        print(f"\n✅ 网格搜索 Top {len(df)}:")
        print(df.to_string(index=False))


class TestWalkForward:
    """测试 Walk-forward"""
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_walk_forward(self):
        """测试 Walk-forward"""
        from quant_trader.backtest import WalkForwardEngine
        
        engine = WalkForwardEngine(
            symbol="2800.HK",
            train_months=6,
            test_months=2,
            step_months=2,
            provider_name="stooq",
        )
        
        result = engine.run("2023-01-01", "2025-01-01")
        
        assert result is not None
        assert result.summary["total_windows"] >= 2
        
        print(f"\n✅ Walk-forward: {result.summary['total_windows']} 窗口")
        print(f"平均收益: {result.summary['avg_return']:.2f}%")
        print(f"平均回撤: {result.summary['avg_max_drawdown']:.2f}%")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
