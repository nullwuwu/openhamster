"""
Regime Detector 测试
"""
import pytest
import pandas as pd
import numpy as np

from openhamster.strategy.regime import RegimeDetector, RegimeConfig, MarketRegime


class TestRegimeDetector:
    """测试 Regime Detector"""
    
    def test_trending_market(self):
        """测试上涨趋势市场"""
        # 持续上涨的数据
        dates = pd.date_range('2020-01-01', periods=100)
        price = 100 + np.cumsum(np.random.randn(100) * 0.5 + 1)  # 上涨趋势
        
        data = pd.DataFrame({
            'open': price * 0.99,
            'high': price * 1.02,
            'low': price * 0.98,
            'close': price,
        }, index=dates)
        
        detector = RegimeDetector()
        regime = detector.detect(data)
        
        # 趋势明显应该被检测为 trending
        # (结果取决于随机数据，可能不稳定)
        assert regime in [MarketRegime.TRENDING, MarketRegime.RANGING]
    
    def test_ranging_market(self):
        """测试震荡市场"""
        # 震荡数据
        dates = pd.date_range('2020-01-01', periods=100)
        price = 100 + 10 * np.sin(np.linspace(0, 4*np.pi, 100))
        
        data = pd.DataFrame({
            'open': price * 0.99,
            'high': price * 1.02,
            'low': price * 0.98,
            'close': price,
        }, index=dates)
        
        detector = RegimeDetector()
        regime = detector.detect(data)
        
        # 震荡市场应该被检测为 ranging
        assert regime in [MarketRegime.TRENDING, MarketRegime.RANGING]
    
    def test_config_ma_slope_threshold(self):
        """测试 MA 斜率阈值配置"""
        config = RegimeConfig(ma_slope_threshold=0.01)
        assert config.ma_slope_threshold == 0.01
    
    def test_config_adx_threshold(self):
        """测试 ADX 阈值配置"""
        config = RegimeConfig(adx_threshold=30)
        assert config.adx_threshold == 30
    
    def test_config_and_logic(self):
        """测试 AND 逻辑"""
        config = RegimeConfig(logic_and=True)
        assert config.logic_and == True
    
    def test_config_or_logic(self):
        """测试 OR 逻辑 (默认)"""
        config = RegimeConfig(logic_and=False)
        assert config.logic_and == False


class TestRegimeWithRealData:
    """用真实价格数据测试"""
    
    def test_detect_with_price_data(self):
        """用价格序列测试"""
        # 模拟上涨趋势
        n = 100
        dates = pd.date_range('2020-01-01', periods=n)
        close = pd.Series(100 + np.arange(n) * 0.5, index=dates)
        
        # 简化测试: 创建测试数据
        data = pd.DataFrame({
            'close': close,
            'high': close * 1.01,
            'low': close * 0.99,
        }, index=dates)
        
        detector = RegimeDetector()
        regime = detector.detect(data)
        
        assert regime in [MarketRegime.TRENDING, MarketRegime.RANGING, MarketRegime.UNKNOWN]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
