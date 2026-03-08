"""
策略选择器

根据市场环境选择合适的策略
"""
from __future__ import annotations
import logging
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from .market_regime import Regime

logger = logging.getLogger("quant_trader.strategy_selector")


class Strategy(Enum):
    """可选策略"""
    DUAL_MA = "DUAL_MA"          # 双均线
    RSI = "RSI"                  # RSI 策略
    MACD = "MACD"                # MACD 策略
    MEAN_REVERSION = "MEAN_REV"  # 均值回归


@dataclass
class StrategyRecommendation:
    """策略推荐"""
    strategy: Strategy
    weight: float  # 权重 0-1
    reason: str


class StrategySelector:
    """
    策略选择器
    
    根据市场环境选择合适的策略
    """
    
    def __init__(self, high_vol_threshold: float = 0.03):
        """
        Args:
            high_vol_threshold: 高波动阈值
        """
        self.high_vol_threshold = high_vol_threshold
    
    def select(
        self,
        market_regime: Regime,
        volatility: float,
    ) -> list[StrategyRecommendation]:
        """
        选择策略
        
        Args:
            market_regime: 市场环境 (Regime 枚举)
            volatility: 波动率
            
        Returns:
            list of StrategyRecommendation
        """
        high_vol = volatility > self.high_vol_threshold
        
        if market_regime == Regime.TRENDING_UP:
            # 上涨趋势: 追涨策略
            weights = {
                Strategy.DUAL_MA: 0.3 if high_vol else 0.5,
                Strategy.MACD: 0.2 if high_vol else 0.3,
                Strategy.MEAN_REVERSION: 0.3 if high_vol else 0.1,
                Strategy.RSI: 0.2,
            }
        
        elif market_regime == Regime.TRENDING_DOWN:
            # 下跌趋势: 观望或做空
            weights = {
                Strategy.RSI: 0.4,
                Strategy.MEAN_REVERSION: 0.3 if high_vol else 0.2,
                Strategy.DUAL_MA: 0.3 if high_vol else 0.2,
                Strategy.MACD: 0.0,
            }
        
        else:  # RANGING - 震荡市
            # 震荡市: 高抛低吸
            weights = {
                Strategy.MEAN_REVERSION: 0.4 if high_vol else 0.3,
                Strategy.RSI: 0.3,
                Strategy.DUAL_MA: 0.2,
                Strategy.MACD: 0.1,
            }
        
        # 构建返回
        regime_name = market_regime.value
        vol_str = "高波动" if high_vol else "低波动"
        
        recommendations = []
        for strategy, weight in weights.items():
            if weight > 0:
                recommendations.append(StrategyRecommendation(
                    strategy=strategy,
                    weight=weight,
                    reason=f"{regime_name} + {vol_str}",
                ))
        
        return recommendations


# 全局实例
_strategy_selector: Optional[StrategySelector] = None


def get_strategy_selector() -> StrategySelector:
    """获取全局策略选择器实例"""
    global _strategy_selector
    if _strategy_selector is None:
        _strategy_selector = StrategySelector()
    return _strategy_selector
