"""
Stooq Provider 测试

验证 Stooq 数据源能正确获取港股数据
"""
import pytest
import pandas as pd
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.data import StooqProvider, get_provider


class TestStooqProvider:
    """测试 StooqProvider"""
    
    def test_provider_interface(self):
        """验证 StooqProvider 实现接口"""
        provider = StooqProvider()
        assert provider.name == "stooq"
        assert hasattr(provider, 'fetch_ohlcv')
    
    def test_get_provider_factory(self):
        """验证 get_provider 工厂函数"""
        provider = get_provider("stooq")
        assert isinstance(provider, StooqProvider)
        assert provider.name == "stooq"
    
    def test_hk_ticker_format(self):
        """测试港股代码格式"""
        provider = StooqProvider()
        
        # 验证代码会被转为大写
        data = provider.fetch_ohlcv("2800.hk", "2025-01-01", "2025-01-10")
        
        assert isinstance(data, pd.DataFrame)


class TestStooqProviderIntegration:
    """StooqProvider 集成测试 (需要网络)"""
    
    @pytest.mark.integration
    def test_fetch_2800hk(self):
        """测试获取 2800.HK 港股数据"""
        provider = StooqProvider()
        
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
        
        print(f"\n✅ Stooq: 成功获取 {len(data)} 行 2800.HK 数据")
        print(f"日期范围: {data.index.min()} 到 {data.index.max()}")
        print(f"前3行:\n{data.head(3)}")
    
    @pytest.mark.integration
    def test_fetch_us_stock(self):
        """测试获取美股数据 (Stooq 优势)"""
        provider = StooqProvider()
        
        # 苹果
        data = provider.fetch_ohlcv(
            "AAPL",
            "2025-01-01",
            "2025-03-01"
        )
        
        assert len(data) > 30, f"Expected >30 rows, got {len(data)}"
        print(f"\n✅ Stooq: 成功获取 {len(data)} 行 AAPL 数据")


class TestStooqMock:
    """StooqProvider 单元测试 (Mock)"""
    
    @patch('quant_trader.data.stooq_provider.pdr_data.DataReader')
    def test_fetch_ohlcv_success(self, mock_reader):
        """测试成功获取数据 (Mock)"""
        # Mock 返回数据 (带正确的索引名)
        dates = pd.date_range('2024-01-01', '2024-01-10', freq='D')
        mock_data = pd.DataFrame({
            'Open': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            'High': [110, 111, 112, 113, 114, 115, 116, 117, 118, 119],
            'Low': [90, 91, 92, 93, 94, 95, 96, 97, 98, 99],
            'Close': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            'Volume': [1000000] * 10,
        }, index=pd.DatetimeIndex(dates, name='Date'))  # 关键：添加 name='Date'
        
        mock_reader.return_value = mock_data
        
        provider = StooqProvider()
        data = provider.fetch_ohlcv("SPY", "2024-01-01", "2024-01-10")
        
        # 验证
        assert len(data) == 10
        assert 'open' in data.columns
        assert 'close' in data.columns
        assert isinstance(data.index, pd.DatetimeIndex)
    
    @patch('quant_trader.data.stooq_provider.pdr_data.DataReader')
    def test_fetch_ohlcv_empty(self, mock_reader):
        """测试空数据"""
        mock_reader.return_value = pd.DataFrame()
        
        provider = StooqProvider()
        
        with pytest.raises(RuntimeError):
            provider.fetch_ohlcv("INVALID", "2024-01-01", "2024-01-10")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
