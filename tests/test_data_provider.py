"""
Data Provider 测试

验证 DataProvider 抽象层和各实现
"""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.data import DataProvider, YFinanceProvider, TwelveDataProvider


class TestDataProvider:
    """测试 DataProvider 抽象"""
    
    def test_yfinance_provider_interface(self):
        """验证 YFinanceProvider 实现接口"""
        provider = YFinanceProvider()
        assert provider.name == "yfinance"
        assert hasattr(provider, 'fetch_ohlcv')
    
    def test_twelve_data_provider_interface(self):
        """验证 TwelveDataProvider 实现接口"""
        with patch.dict(os.environ, {'TWELVE_DATA_API_KEY': 'test_key'}):
            provider = TwelveDataProvider()
            assert provider.name == "twelve_data"
            assert hasattr(provider, 'fetch_ohlcv')


class TestYFinanceProvider:
    """测试 YFinanceProvider"""
    
    @patch('quant_trader.data.yfinance_provider.yf.download')
    def test_fetch_ohlcv_success(self, mock_download):
        """测试成功获取数据"""
        # Mock 返回数据
        dates = pd.date_range('2024-01-01', '2024-01-10')
        mock_data = pd.DataFrame({
            'Open': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            'High': [110, 111, 112, 113, 114, 115, 116, 117, 118, 119],
            'Low': [90, 91, 92, 93, 94, 95, 96, 97, 98, 99],
            'Close': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            'Volume': [1000000] * 10,
        }, index=dates)
        
        mock_download.return_value = mock_data
        
        provider = YFinanceProvider()
        data = provider.fetch_ohlcv("SPY", "2024-01-01", "2024-01-10")
        
        # 验证
        assert len(data) == 10
        assert 'open' in data.columns
        assert 'high' in data.columns
        assert 'low' in data.columns
        assert 'close' in data.columns
        assert 'volume' in data.columns
    
    @patch('quant_trader.data.yfinance_provider.yf.download')
    def test_fetch_ohlcv_empty(self, mock_download):
        """测试空数据"""
        mock_download.return_value = pd.DataFrame()
        
        provider = YFinanceProvider()
        
        with pytest.raises(RuntimeError):
            provider.fetch_ohlcv("INVALID", "2024-01-01", "2024-01-10")


class TestTwelveDataProvider:
    """测试 TwelveDataProvider"""
    
    @patch('quant_trader.data.twelve_data_provider.requests.get')
    def test_fetch_ohlcv_success(self, mock_get):
        """测试成功获取数据"""
        # Mock API 响应
        mock_response = Mock()
        mock_response.json.return_value = {
            "code": 200,
            "values": [
                {"datetime": "2024-01-01", "open": "100", "high": "110", "low": "90", "close": "100", "volume": "1000000"},
                {"datetime": "2024-01-02", "open": "101", "high": "111", "low": "91", "close": "101", "volume": "1000000"},
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        with patch.dict(os.environ, {'TWELVE_DATA_API_KEY': 'test_key'}):
            provider = TwelveDataProvider(api_key='test_key')
            data = provider.fetch_ohlcv("SPY", "2024-01-01", "2024-01-02")
        
        # 验证
        assert len(data) == 2
        assert 'open' in data.columns
        assert 'close' in data.columns
        assert isinstance(data.index, pd.DatetimeIndex)
    
    @patch('quant_trader.data.twelve_data_provider.requests.get')
    def test_fetch_ohlcv_api_error(self, mock_get):
        """测试 API 错误"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "code": 400,
            "message": "Invalid symbol"
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        with patch.dict(os.environ, {'TWELVE_DATA_API_KEY': 'test_key'}):
            provider = TwelveDataProvider(api_key='test_key')
            
            with pytest.raises(RuntimeError, match="API error"):
                provider.fetch_ohlcv("INVALID", "2024-01-01", "2024-01-02")


class TestDataFrameFormat:
    """测试 DataFrame 格式标准化"""
    
    def test_normalize_columns(self):
        """测试列名标准化"""
        provider = YFinanceProvider()
        
        # 大写列名
        data = pd.DataFrame({
            'Open': [100],
            'High': [110],
            'Low': [90],
            'Close': [100],
            'Volume': [1000000],
        }, index=pd.date_range('2024-01-01', periods=1))
        
        result = provider._normalize_columns(data)
        
        assert 'open' in result.columns
        assert 'high' in result.columns
        assert 'low' in result.columns
        assert 'close' in result.columns
        assert 'volume' in result.columns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
