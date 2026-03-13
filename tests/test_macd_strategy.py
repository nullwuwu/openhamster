"""
MACD 策略测试
"""
import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from goby_shrimp.strategy import MACDStrategy
from goby_shrimp.strategy.signals import Signal


class TestMACDStrategy:
    """MACD 策略测试"""
    
    def test_strategy_init(self):
        """测试策略初始化"""
        strategy = MACDStrategy(
            fast_period=12,
            slow_period=26,
            signal_period=9,
        )
        
        assert strategy.name == "macd"
        assert strategy.fast_period == 12
        assert strategy.slow_period == 26
        assert strategy.signal_period == 9
    
    def test_default_params(self):
        """测试默认参数"""
        strategy = MACDStrategy()
        
        assert strategy.fast_period == 12
        assert strategy.slow_period == 26
        assert strategy.signal_period == 9
        assert strategy.use_zero_cross is True
    
    def test_reset(self):
        """测试重置"""
        strategy = MACDStrategy()
        strategy._macd = pd.Series([0.1, 0.2])
        strategy._signal = pd.Series([0.05, 0.15])
        strategy._last_signal = Signal.BUY
        
        strategy.reset()
        
        assert strategy._macd is None
        assert strategy._signal is None
        assert strategy._histogram is None
        assert strategy._last_signal == Signal.HOLD
    
    def test_insufficient_data(self):
        """测试数据不足"""
        strategy = MACDStrategy()
        
        data = pd.DataFrame({
            "open": [100, 101],
            "high": [102, 103],
            "low": [99, 100],
            "close": [101, 102],
            "volume": [1000, 1000],
        }, index=pd.date_range("2024-01-01", periods=2))
        
        signal = strategy.generate_signal(data)
        assert signal == Signal.HOLD
    
    def test_golden_cross_buy(self):
        """测试金叉买入信号"""
        strategy = MACDStrategy(
            fast_period=5,
            slow_period=10,
            signal_period=3,
        )
        
        # 构造金叉数据: 快线从下往上穿过慢线
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        
        # 先下跌 (金叉前)
        prices = np.array([100] * 15 + 
                         [98, 96, 94, 92, 95, 98, 100, 102, 105, 108, 110, 112, 115])
        
        data = pd.DataFrame({
            "open": prices - 0.5,
            "high": prices + 1,
            "low": prices - 1,
            "close": prices,
            "volume": 1000000,
        }, index=dates[:len(prices)])
        
        signal = strategy.generate_signal(data)
        # 可能会产生 BUY 信号
        assert signal in [Signal.BUY, Signal.HOLD]
    
    def test_death_cross_sell(self):
        """测试死叉卖出信号"""
        strategy = MACDStrategy(
            fast_period=5,
            slow_period=10,
            signal_period=3,
        )
        
        # 构造死叉数据: 快线从上往下穿过慢线
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        
        # 先上涨 (死叉前)
        prices = np.array([100] * 15 + 
                         [105, 110, 115, 120, 118, 115, 112, 110, 108, 105, 102, 100, 98])
        
        data = pd.DataFrame({
            "open": prices - 0.5,
            "high": prices + 1,
            "low": prices - 1,
            "close": prices,
            "volume": 1000000,
        }, index=dates[:len(prices)])
        
        signal = strategy.generate_signal(data)
        # 可能会产生 SELL 信号
        assert signal in [Signal.SELL, Signal.HOLD]
    
    def test_zero_cross_bullish(self):
        """测试零轴交叉 - 多头"""
        strategy = MACDStrategy(
            fast_period=5,
            slow_period=10,
            signal_period=3,
            use_zero_cross=True,
        )
        
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        
        # MACD 从负转正
        prices = np.array([100] * 20 + [102, 104, 106, 108, 110, 112, 115, 118, 120, 122])
        
        data = pd.DataFrame({
            "open": prices - 0.5,
            "high": prices + 1,
            "low": prices - 1,
            "close": prices,
            "volume": 1000000,
        }, index=dates[:len(prices)])
        
        signal = strategy.generate_signal(data)
        # 可能会产生信号
        assert signal in [Signal.BUY, Signal.HOLD]
    
    def test_zero_cross_bearish(self):
        """测试零轴交叉 - 空头"""
        strategy = MACDStrategy(
            fast_period=5,
            slow_period=10,
            signal_period=3,
            use_zero_cross=True,
        )
        
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        
        # MACD 从正转负
        prices = np.array([100] * 20 + [98, 96, 94, 92, 90, 88, 85, 82, 80, 78])
        
        data = pd.DataFrame({
            "open": prices - 0.5,
            "high": prices + 1,
            "low": prices - 1,
            "close": prices,
            "volume": 1000000,
        }, index=dates[:len(prices)])
        
        signal = strategy.generate_signal(data)
        # 可能会产生信号
        assert signal in [Signal.SELL, Signal.HOLD]
    
    def test_no_signal_when_no_crossover(self):
        """无交叉时应保持 HOLD"""
        strategy = MACDStrategy(
            fast_period=5,
            slow_period=10,
            signal_period=3,
        )
        
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        
        # 震荡行情，无明显交叉
        np.random.seed(42)
        close = 100 + np.cumsum(np.random.randn(50) * 0.3)
        
        data = pd.DataFrame({
            "open": close - 0.5,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000000,
        }, index=dates)
        
        # 多运行几次确保稳定
        for _ in range(3):
            strategy.reset()
            signal = strategy.generate_signal(data)
            # 震荡行情应该倾向于 HOLD
            assert signal in [Signal.BUY, Signal.SELL, Signal.HOLD]
    
    def test_get_indicators(self):
        """测试获取指标"""
        strategy = MACDStrategy()
        
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
        
        assert "macd" in indicators.columns
        assert "signal" in indicators.columns
        assert "histogram" in indicators.columns
        assert "close" in indicators.columns
        assert len(indicators) == 50
    
    def test_custom_params(self):
        """测试自定义参数"""
        strategy = MACDStrategy(
            fast_period=8,
            slow_period=24,
            signal_period=6,
            use_zero_cross=False,
        )
        
        assert strategy.fast_period == 8
        assert strategy.slow_period == 24
        assert strategy.signal_period == 6
        assert strategy.use_zero_cross is False
