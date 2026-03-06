"""
AKShare Provider 测试

验证 AKShare 数据源能正确获取港股数据
"""
import pytest
import pandas as pd
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.data import AKShareProvider, get_provider


class TestAKShareProvider:
    """测试 AKShareProvider"""
    
    def test_provider_interface(self):
        """验证 AKShareProvider 实现接口"""
        provider = AKShareProvider()
        assert provider.name == "akshare"
        assert hasattr(provider, 'fetch_ohlcv')
    
    def test_get_provider_factory(self):
        """验证 get_provider 工厂函数"""
        provider = get_provider("akshare")
        assert isinstance(provider, AKShareProvider)
        assert provider.name == "akshare"
    
    def test_default_provider(self):
        """验证默认 provider 是 AKShare"""
        provider = get_provider()
        assert isinstance(provider, AKShareProvider)
    
    def test_hk_ticker_conversion(self):
        """测试港股代码转换"""
        from quant_trader.data.akshare_provider import _convert_hk_ticker
        
        assert _convert_hk_ticker("2800") == "02800"
        assert _convert_hk_ticker("2800.HK") == "02800"
        assert _convert_hk_ticker("02800") == "02800"
        assert _convert_hk_ticker("5") == "00005"
    
    def test_invalid_ticker(self):
        """测试无效代码"""
        provider = AKShareProvider()
        
        with pytest.raises(Exception):
            # 无效代码应该抛出异常
            provider.fetch_ohlcv("INVALID999", "2024-01-01", "2024-01-10")


class TestAKShareProviderIntegration:
    """AKShareProvider 集成测试 (需要网络)"""
    
    @pytest.mark.integration
    def test_fetch_2800hk(self):
        """测试获取 2800.HK 港股数据"""
        provider = AKShareProvider()
        
        # 过去 3 年
        end = datetime.now()
        start = end - timedelta(days=3*365)
        
        data = provider.fetch_ohlcv(
            "2800.HK",
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d")
        )
        
        # 验证
        assert len(data) > 700, f"Expected >700 rows, got {len(data)}"
        assert 'open' in data.columns
        assert 'high' in data.columns
        assert 'low' in data.columns
        assert 'close' in data.columns
        assert 'volume' in data.columns
        
        # 验证无空值
        null_count = data[["open", "high", "low", "close", "volume"]].isnull().sum().sum()
        assert null_count == 0, f"Found {null_count} null values"
        
        print(f"\n✅ AKShare: 成功获取 {len(data)} 行 2800.HK 数据")
        print(f"日期范围: {data.index.min()} 到 {data.index.max()}")
        print(f"前3行:\n{data.head(3)}")
    
    @pytest.mark.integration
    def test_fetch_another_hk_stock(self):
        """测试获取其他港股数据"""
        provider = AKShareProvider()
        
        # 腾讯控股 (0700.HK)
        data = provider.fetch_ohlcv(
            "0700.HK",
            "2025-01-01",
            "2025-03-01"
        )
        
        assert len(data) > 30, f"Expected >30 rows, got {len(data)}"
        print(f"\n✅ AKShare: 成功获取 {len(data)} 行 0700.HK 数据")


class TestProviderRegistry:
    """测试 Provider 注册表"""
    
    def test_list_providers(self):
        """测试列出所有可用 providers"""
        from quant_trader.data import _PROVIDERS
        
        assert "akshare" in _PROVIDERS
        assert "stooq" in _PROVIDERS
        assert "yfinance" in _PROVIDERS
        assert "twelve_data" in _PROVIDERS
    
    def test_unknown_provider(self):
        """测试未知 provider 抛出异常"""
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("unknown_provider")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
