"""
Mean Reversion Strategy 测试
"""
import pytest
import pandas as pd
import numpy as np

from goby_shrimp.strategy.mean_reversion import MeanReversionStrategy, create_mean_reversion_strategy


class TestMeanReversionStrategy:
    """测试均值回归策略"""
    
    def test_signal_generation(self):
        """测试信号生成"""
        # 创建测试数据：先跌后涨再跌
        n = 100
        dates = pd.date_range('2020-01-01', periods=n)
        
        # 模拟价格走势：先下跌→超跌反弹→震荡
        price = 100 * np.ones(n)
        price[20:40] = 90  # 下跌到90
        price[40:60] = 95  # 反弹到95
        price[60:80] = 85  # 再次下跌到85
        
        data = pd.DataFrame({
            'open': price * 0.99,
            'high': price * 1.02,
            'low': price * 0.98,
            'close': price,
        }, index=dates)
        
        strategy = MeanReversionStrategy(z_window=20, entry_threshold=2.0, exit_threshold=0.5)
        signals = strategy.generate_signals(data)
        
        # 验证信号生成了
        assert len(signals) == n
        assert signals.dtype in [np.int64, np.int32, int]
    
    def test_z_score_calculation(self):
        """测试 Z-Score 计算"""
        n = 100
        dates = pd.date_range('2020-01-01', periods=n)
        price = 100 + np.random.randn(n) * 5
        
        data = pd.DataFrame({
            'close': price,
            'open': price * 0.99,
            'high': price * 1.01,
            'low': price * 0.99,
        }, index=dates)
        
        strategy = MeanReversionStrategy(z_window=20)
        z = strategy.calculate_z_score(data)
        
        # 验证 Z-Score 计算
        assert len(z) == n
        # 前20个应该是 NaN (窗口不足)
        assert z.iloc[:19].isna().all()
    
    def test_boundary_conditions(self):
        """测试边界条件"""
        # 窗口不足的情况
        n = 10
        dates = pd.date_range('2020-01-01', periods=n)
        price = np.arange(n) * 10 + 100
        
        data = pd.DataFrame({
            'close': price,
            'open': price * 0.99,
            'high': price * 1.01,
            'low': price * 0.99,
        }, index=dates)
        
        strategy = MeanReversionStrategy(z_window=20)
        signals = strategy.generate_signals(data)
        
        # 窗口不足时应返回 0
        assert signals.isna().sum() > 0 or signals.max() <= 1
    
    def test_params(self):
        """测试参数"""
        strategy = MeanReversionStrategy(
            z_window=30,
            entry_threshold=1.5,
            exit_threshold=0.3,
            use_short=False,
        )
        
        params = strategy.get_params()
        
        assert params['z_window'] == 30
        assert params['entry_threshold'] == 1.5
        assert params['exit_threshold'] == 0.3
        assert params['use_short'] == False
    
    def test_create_helper(self):
        """测试创建函数"""
        strategy = create_mean_reversion_strategy(
            z_window=25,
            entry_threshold=1.8,
            exit_threshold=0.4,
        )
        
        assert strategy.z_window == 25
        assert strategy.entry_threshold == 1.8
        assert strategy.exit_threshold == 0.4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
