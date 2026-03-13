"""
回测引擎测试
"""
import pytest
import pandas as pd
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from goby_shrimp.strategy import MACrossStrategy
from goby_shrimp.backtest import Backtester, BacktestResult


class TestBacktester:
    """测试回测引擎"""
    
    def test_backtester_init(self):
        """测试回测引擎初始化"""
        strategy = MACrossStrategy()
        backtester = Backtester(
            strategy=strategy,
            symbol="2800.HK",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_capital=1_000_000,
        )
        
        assert backtester.symbol == "2800.HK"
        assert backtester.initial_capital == 1_000_000
        assert backtester.strategy == strategy
    
    @patch('goby_shrimp.backtest.backtester.get_provider')
    def test_backtest_run_with_mock(self, mock_get_provider):
        """测试回测运行 (Mock)"""
        # Mock 数据
        dates = pd.date_range('2024-01-01', periods=30, freq='D')
        mock_data = pd.DataFrame({
            'open': [100] * 30,
            'high': [105] * 30,
            'low': [95] * 30,
            'close': list(range(100, 130)),
            'volume': [1000000] * 30,
        }, index=dates)
        
        # Mock provider
        mock_provider = MagicMock()
        mock_provider.fetch_ohlcv.return_value = mock_data
        mock_get_provider.return_value = mock_provider
        
        # 创建回测
        strategy = MACrossStrategy(short_window=5, long_window=10)
        backtester = Backtester(
            strategy=strategy,
            symbol="TEST",
            start_date="2024-01-01",
            end_date="2024-01-30",
            initial_capital=100000,
            provider_name="stooq",
        )
        
        # 运行回测
        result = backtester.run()
        
        # 验证
        assert isinstance(result, BacktestResult)
        assert result.symbol == "TEST"
        assert result.initial_capital == 100000
        assert result.total_return is not None
        assert not result.equity_curve.empty
    
    def test_backtest_result_summary(self):
        """测试结果摘要"""
        result = BacktestResult(
            symbol="TEST",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_capital=100000,
            final_value=110000,
            total_return=10.0,
            annual_return=10.0,
            max_drawdown=-5.0,
            sharpe_ratio=1.5,
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
        )
        
        summary = result.summary()
        assert "TEST" in summary
        assert "10.00%" in summary  # 总收益率
        assert "10" in summary  # 交易次数

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
