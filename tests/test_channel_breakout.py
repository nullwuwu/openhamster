"""
Channel Breakout Strategy 测试
"""
import pytest
import pandas as pd
import numpy as np

from goby_shrimp.strategy.channel_breakout import ChannelBreakoutStrategy, create_channel_breakout_strategy


class TestChannelBreakoutStrategy:
    """测试通道突破策略"""
    
    def test_signal_generation(self):
        """测试信号生成"""
        n = 100
        dates = pd.date_range('2020-01-01', periods=n)
        
        # 上涨趋势
        price = 100 + np.arange(n) * 0.5
        
        data = pd.DataFrame({
            'open': price * 0.99,
            'high': price * 1.02,
            'low': price * 0.98,
            'close': price,
        }, index=dates)
        
        strategy = ChannelBreakoutStrategy(channel_window=20)
        signals = strategy.generate_signals(data)
        
        assert len(signals) == n
    
    def test_atr_calculation(self):
        """测试 ATR 计算"""
        n = 50
        dates = pd.date_range('2020-01-01', periods=n)
        
        price = 100 + np.random.randn(n) * 2
        high = price + np.random.rand(n) * 2
        low = price - np.random.rand(n) * 2
        
        data = pd.DataFrame({
            'close': price,
            'high': high,
            'low': low,
        }, index=dates)
        
        strategy = ChannelBreakoutStrategy(atr_window=14)
        # 简单验证不报错
        signals = strategy.generate_signals(data)
        assert len(signals) == n
    
    def test_channel_boundaries(self):
        """测试通道边界"""
        n = 50
        dates = pd.date_range('2020-01-01', periods=n)
        
        price = np.arange(n) * 2 + 100
        high = price + 5
        low = price - 5
        
        data = pd.DataFrame({
            'close': price,
            'high': high,
            'low': low,
        }, index=dates)
        
        strategy = ChannelBreakoutStrategy(channel_window=20)
        signals = strategy.generate_signals(data)
        
        # 验证信号在窗口足够后生成
        assert signals.iloc[:20].isna().sum() > 0 or signals.iloc[0] == 0
    
    def test_empty_data(self):
        """测试空数据边界"""
        data = pd.DataFrame(columns=['open', 'high', 'low', 'close'])
        
        strategy = ChannelBreakoutStrategy()
        signals = strategy.generate_signals(data)
        
        assert len(signals) == 0
    
    def test_params(self):
        """测试参数"""
        strategy = ChannelBreakoutStrategy(
            channel_window=30,
            atr_window=20,
            atr_k=2.5,
        )
        
        params = strategy.get_params()
        
        assert params['channel_window'] == 30
        assert params['atr_window'] == 20
        assert params['atr_k'] == 2.5
    
    def test_create_helper(self):
        """测试创建函数"""
        strategy = create_channel_breakout_strategy(
            channel_window=25,
            atr_window=14,
            atr_k=2.0,
        )
        
        assert strategy.channel_window == 25
        assert strategy.atr_window == 14
        assert strategy.atr_k == 2.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
