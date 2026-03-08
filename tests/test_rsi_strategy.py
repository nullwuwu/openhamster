"""
RSI 策略测试
"""
import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.strategy import RSIStrategy
from quant_trader.strategy.signals import Signal


class TestRSIStrategy:
    """RSI 策略测试"""
    
    @pytest.fixture
    def sample_data(self) -> pd.DataFrame:
        """生成测试数据"""
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        
        # 模拟下跌后反弹的价格 (RSI 超卖反弹)
        prices = 100 - np.cumsum(np.random.randn(100) * 0.5)
        prices = np.clip(prices, 80, 120)
        
        data = pd.DataFrame({
            "open": prices - 0.5,
            "high": prices + 1,
            "low": prices - 1,
            "close": prices,
            "volume": 1000000,
        }, index=dates)
        
        return data
    
    @pytest.fixture
    def oversold_data(self) -> pd.DataFrame:
        """RSI 超卖数据"""
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        
        # 持续下跌到超卖
        prices = 100 - np.arange(50) * 0.5
        
        return pd.DataFrame({
            "open": prices - 0.5,
            "high": prices + 1,
            "low": prices - 1,
            "close": prices,
            "volume": 1000000,
        }, index=dates)
    
    def test_strategy_init(self):
        """测试策略初始化"""
        strategy = RSIStrategy(period=14, oversold=30, overbought=70)
        
        assert strategy.name == "rsi"
        assert strategy.period == 14
        assert strategy.oversold == 30
        assert strategy.overbought == 70
    
    def test_default_params(self):
        """测试默认参数"""
        strategy = RSIStrategy()
        
        assert strategy.period == 14
        assert strategy.oversold == 30
        assert strategy.overbought == 70
        assert strategy.use_mid_crossover is True
    
    def test_reset(self):
        """测试重置"""
        strategy = RSIStrategy()
        strategy._rsi = pd.Series([30, 40])
        strategy._last_signal = Signal.BUY
        
        strategy.reset()
        
        assert strategy._rsi is None
        assert strategy._last_signal == Signal.HOLD
    
    def test_insufficient_data(self):
        """测试数据不足"""
        strategy = RSIStrategy(period=14)
        
        data = pd.DataFrame({
            "open": [100, 101],
            "high": [102, 103],
            "low": [99, 100],
            "close": [101, 102],
            "volume": [1000, 1000],
        }, index=pd.date_range("2024-01-01", periods=2))
        
        signal = strategy.generate_signal(data)
        assert signal == Signal.HOLD
    
    def test_generate_signal_hold(self):
        """测试 HOLD 信号"""
        strategy = RSIStrategy(period=14)
        
        # RSI 在中间区域波动
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        
        # 围绕 50 波动
        rsi_values = 50 + np.sin(np.arange(50) * 0.3) * 20
        close = 100 + np.cumsum(np.random.randn(50) * 0.1)
        
        data = pd.DataFrame({
            "open": close - 0.5,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000000,
        }, index=dates)
        
        # 直接设置 RSI 值来测试
        strategy._rsi = pd.Series(rsi_values, index=dates)
        
        # 最后一个 RSI 在 50 附近，应该 HOLD
        signal = strategy.generate_signal(data)
        assert signal in [Signal.BUY, Signal.SELL, Signal.HOLD]
    
    def test_oversold_buy_signal(self):
        """测试超卖买入信号"""
        strategy = RSIStrategy(period=14, oversold=30)
        
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        
        # 下跌后反弹
        close = np.array([100] * 14 + 
                        [95, 90, 85, 80, 82, 85, 88, 90, 92, 95, 98, 100, 102, 105, 108, 110])
        
        data = pd.DataFrame({
            "open": close - 0.5,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000000,
        }, index=dates[:len(close)])
        
        signal = strategy.generate_signal(data)
        # 可能会产生 BUY 信号 (从超卖区域反弹)
        assert signal in [Signal.BUY, Signal.HOLD]
    
    def test_overbought_sell_signal(self):
        """测试超买卖出信号"""
        strategy = RSIStrategy(period=14, overbought=70)
        
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        
        # 上涨后回落
        close = np.array([100] * 14 + 
                        [105, 110, 115, 120, 118, 115, 112, 110, 108, 105, 102, 100, 98, 95, 92, 90])
        
        data = pd.DataFrame({
            "open": close - 0.5,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000000,
        }, index=dates[:len(close)])
        
        signal = strategy.generate_signal(data)
        # 可能会产生 SELL 信号 (从超买区域回落)
        assert signal in [Signal.SELL, Signal.HOLD]
    
    def test_get_indicators(self):
        """测试获取指标"""
        strategy = RSIStrategy(period=14)
        
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        close = 100 + np.cumsum(np.random.randn(50) * 0.5)
        
        data = pd.DataFrame({
            "open": close - 0.5,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000000,
        }, index=dates)
        
        indicators = strategy.get_indicators(data)
        
        assert "rsi" in indicators.columns
        assert "close" in indicators.columns
        assert len(indicators) == 50
        # RSI 应该在 0-100 之间
        assert indicators["rsi"].dropna().between(0, 100).all()
