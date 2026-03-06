"""
数据源模块

统一的数据提供者接口，支持多种数据源
"""
from .base import DataProvider
from .yfinance_provider import YFinanceProvider
from .twelve_data_provider import TwelveDataProvider
from .akshare_provider import AKShareProvider
from .stooq_provider import StooqProvider

__all__ = [
    "DataProvider",
    "YFinanceProvider", 
    "TwelveDataProvider",
    "AKShareProvider",
    "StooqProvider",
    "get_provider",
]

# Provider 注册表
_PROVIDERS = {
    "yfinance": YFinanceProvider,
    "twelve_data": TwelveDataProvider,
    "akshare": AKShareProvider,
    "stooq": StooqProvider,
}

# 默认 provider
DEFAULT_PROVIDER = "akshare"


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
