"""
市场环境判断器

判断当前市场状态
"""
from __future__ import annotations
import logging
from typing import Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("quant_trader.market_regime")


class Regime(Enum):
    """市场环境"""
    TRENDING_UP = "TRENDING_UP"      # 上涨趋势
    TRENDING_DOWN = "TRENDING_DOWN"  # 下跌趋势
    RANGING = "RANGING"              # 震荡


@dataclass
class RegimeResult:
    """市场环境结果"""
    regime: Regime
    confidence: float  # 0-1
    reason: str
    indicators: dict


class MarketRegime:
    """
    市场环境判断器
    
    判断当前市场是趋势还是震荡
    """
    
    def __init__(self):
        pass
    
    def analyze(
        self,
        ohlcv: dict,
    ) -> Optional[RegimeResult]:
        """
        分析市场环境
        
        Args:
            ohlcv: K线数据
            
        Returns:
            RegimeResult or None
        """
        if ohlcv is None or len(ohlcv.get("close", [])) < 60:
            logger.warning("数据不足，无法判断市场环境")
            return None
        
        close = ohlcv["close"]
        
        # 计算指标
        ma20 = self._ma(close, 20)
        ma60 = self._ma(close, 60)
        
        # 价格位置
        current_price = close[-1]
        
        # 计算波动率
        volatility = self._volatility(close, 20)
        
        # 计算趋势强度
        trend_strength = self._trend_strength(close, ma20, ma60)
        
        # 综合投票判断环境
        return self._determine_regime(
            current_price=current_price,
            ma20=ma20,
            ma60=ma60,
            volatility=volatility,
            trend_strength=trend_strength,
        )
    
    def _ma(self, data: list, period: int) -> float:
        """移动平均"""
        if len(data) < period:
            return data[-1] if data else 0
        return sum(data[-period:]) / period
    
    def _volatility(self, data: list, period: int = 20) -> float:
        """波动率 (标准差 / 均值)"""
        if len(data) < period:
            return 0
        
        recent = data[-period:]
        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)
        std = variance ** 0.5
        
        return std / mean if mean > 0 else 0
    
    def _trend_strength(self, close: list, ma20: float, ma60: float) -> float:
        """
        趋势强度
        
        Returns:
            -1 到 1: 负=下跌, 正=上涨
        """
        if len(close) < 60:
            return 0
        
        # 比较最近 20 天和 60 天前的价格
        price_change_20d = (close[-1] - close[-20]) / close[-20] if len(close) >= 20 else 0
        price_change_60d = (close[-1] - close[-60]) / close[-60] if len(close) >= 60 else 0
        
        # 趋势强度 = 短期变化 + 长期变化
        strength = price_change_20d * 0.6 + price_change_60d * 0.4
        
        return max(-1, min(1, strength))  # 限制在 -1 到 1
    
    def _determine_regime(
        self,
        current_price: float,
        ma20: float,
        ma60: float,
        volatility: float,
        trend_strength: float,
    ) -> RegimeResult:
        """综合多指标投票判断市场环境"""
        
        # 各项指标打分
        above_ma20 = current_price > ma20
        above_ma60 = current_price > ma60
        ma_aligned_up = ma20 > ma60
        ma_aligned_down = ma20 < ma60
        
        # 投票
        bull_score = sum([
            trend_strength > 0.05,
            above_ma20,
            above_ma60,
            ma_aligned_up,
        ])
        
        bear_score = sum([
            trend_strength < -0.05,
            not above_ma20,
            not above_ma60,
            ma_aligned_down,
        ])
        
        # 判断
        if bull_score >= 3:
            regime = Regime.TRENDING_UP
            confidence = bull_score / 4
            reason = f"bull={bull_score}/4"
        elif bear_score >= 3:
            regime = Regime.TRENDING_DOWN
            confidence = bear_score / 4
            reason = f"bear={bear_score}/4"
        else:
            regime = Regime.RANGING
            confidence = 0.7
            reason = f"bull={bull_score}/4 bear={bear_score}/4"
        
        indicators = {
            "ma20": ma20,
            "ma60": ma60,
            "volatility": volatility,
            "trend_strength": trend_strength,
            "above_ma20": above_ma20,
            "above_ma60": above_ma60,
        }
        
        return RegimeResult(
            regime=regime,
            confidence=round(confidence, 2),
            reason=reason,
            indicators=indicators,
        )


# 全局实例
_market_regime: Optional[MarketRegime] = None


def get_market_regime() -> MarketRegime:
    """获取全局市场环境判断器实例"""
    global _market_regime
    if _market_regime is None:
        _market_regime = MarketRegime()
    return _market_regime
