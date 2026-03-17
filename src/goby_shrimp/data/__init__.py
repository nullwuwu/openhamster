"""
数据源模块

统一的数据提供者接口，支持多种数据源
"""
from .base import DataProvider
from .yfinance_provider import YFinanceProvider
from .twelve_data_provider import TwelveDataProvider
from .akshare_provider import AKShareProvider
from .stooq_provider import StooqProvider
from .minshare_provider import MinShareProvider
from .tencent_provider import TencentProvider
from .itick_provider import ITickProvider
from .alphavantage_provider import AlphaVantageProvider
from .tushare_provider import TushareProvider
from .source_manager import DataSourceManager, get_source_manager, reset_source_manager
from .symbols import detect_market, normalize_symbol, normalize_cn_symbol
from .cache import OHLCVCache
from ..config import get_settings

__all__ = [
    "DataProvider",
    "YFinanceProvider", 
    "TwelveDataProvider",
    "AKShareProvider",
    "StooqProvider",
    "MinShareProvider",
    "TencentProvider",
    "ITickProvider",
    "AlphaVantageProvider",
    "TushareProvider",
    "DataSourceManager",
    "get_source_manager",
    "reset_source_manager",
    "get_provider",
    "detect_market",
    "normalize_symbol",
    "normalize_cn_symbol",
    "OHLCVCache",
]

# Provider 注册表
_PROVIDERS = {
    "yfinance": YFinanceProvider,
    "twelve_data": TwelveDataProvider,
    "akshare": AKShareProvider,
    "stooq": StooqProvider,
    "minshare": MinShareProvider,
    "tencent": TencentProvider,
    "itick": ITickProvider,
    "alphavantage": AlphaVantageProvider,
    "tushare": TushareProvider,
}

# 默认 provider
DEFAULT_PROVIDER = get_settings().data_source.provider


def get_provider(name: str = None, **kwargs) -> DataProvider:
    """
    获取数据源实例
    
    Args:
        name: provider 名称，如 "akshare", "stooq", "yfinance"
              默认为 DEFAULT_PROVIDER (akshare)
        **kwargs: 传递给 provider 构造函数的参数
        
    Returns:
        DataProvider 实例
        
    Raises:
        ValueError: 未知的 provider 名称
    """
    name = name or DEFAULT_PROVIDER
    
    if name not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider: {name}. "
            f"Available: {list(_PROVIDERS.keys())}"
        )
    
    provider_class = _PROVIDERS[name]
    return provider_class(**kwargs)
