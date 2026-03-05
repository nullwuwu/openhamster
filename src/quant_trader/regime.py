"""
Regime Detector - 市场状态判断

判断市场处于趋势市 (trending) 还是震荡市 (ranging)
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from enum import Enum

import pandas as pd
import numpy as np

logger = logging.getLogger("quant_trader.regime")


class MarketRegime(str, Enum):
    """市场状态"""
    TRENDING = "trending"  # 趋势市
    RANGING = "ranging"    # 震荡市
    UNKNOWN = "unknown"


@dataclass
class RegimeConfig:
    """Regime Detector 配置"""
    # MA 斜率阈值
    ma_slope_threshold: float = 0.001  # 日均涨幅 > 0.1% 视为趋势
    
    # ADX 阈值
    adx_threshold: float = 25  # ADX > 25 视为趋势
    
    # 使用什么指标判断
    use_ma_slope: bool = True
    use_adx: bool = True
    
    # 逻辑: AND 还是 OR
    logic_and: bool = False  # True = 两个都满足才算趋势


class RegimeDetector:
    """
    市场状态检测器
    
    使用 MA 斜率 + ADX 判断市场趋势
    
    用法:
        detector = RegimeDetector()
        regime = detector.detect(data)
    """
    
    def __init__(self, config: RegimeConfig | None = None):
        self.config = config or RegimeConfig()
    
    def detect(self, data: pd.DataFrame) -> MarketRegime:
        """
        检测市场状态
        
        Args:
            data: OHLCV 数据
            
        Returns:
            MarketRegime: TRENDING / RANGING / UNKNOWN
        """
        close = data['close']
        
        # 计算 MA 斜率
        ma_slope = self._calc_ma_slope(close)
        
        # 计算 ADX
        adx = self._calc_adx(data)
        
        logger.debug(f"📊 [Regime] MA_slope={ma_slope:.4f}, ADX={adx:.2f}")
        
        # 判断趋势
        is_trending = self._is_trending(ma_slope, adx)
        
        if is_trending:
            return MarketRegime.TRENDING
        else:
            return MarketRegime.RANGING
    
    def _calc_ma_slope(self, close: pd.Series, period: int = 50) -> float:
        """计算 MA 斜率 (日均涨幅)"""
        if len(close) < period:
            return 0.0
        
        ma = close.rolling(period).mean()
        
        # 最近 N 天的斜率
        recent = ma.tail(20)
        if len(recent) < 2:
            return 0.0
        
        # 线性回归斜率
        x = np.arange(len(recent))
        y = recent.values
        
        # 简化: 用 (end - start) / start / days
        slope = (y[-1] - y[0]) / y[0] / len(recent)
        
        return slope
    
    def _calc_adx(self, data: pd.DataFrame, period: int = 14) -> float:
        """计算 ADX (Average Directional Index)"""
        high = data['high']
        low = data['low']
        close = data['close']
        
        if len(close) < period + 1:
            return 0.0
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # +DM, -DM
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        # Smoothed
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        
        # DX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        
        # ADX
        adx = dx.rolling(period).mean()
        
        return adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0.0
    
    def _is_trending(self, ma_slope: float, adx: float) -> bool:
        """判断是否趋势市"""
        ma_ok = self.config.use_ma_slope and (ma_slope > self.config.ma_slope_threshold)
        adx_ok = self.config.use_adx and (adx > self.config.adx_threshold)
        
        if self.config.logic_and:
            return ma_ok and adx_ok
        else:
            # OR 逻辑: 满足任一即可
            return ma_ok or adx_ok
    
    def get_regime_series(self, data: pd.DataFrame) -> pd.Series:
        """获取逐日市场状态序列"""
        regimes = []
        
        for i in range(len(data)):
            if i < 50:  # 需要足够历史数据
                regimes.append(MarketRegime.UNKNOWN)
            else:
                window = data.iloc[:i+1]
                regimes.append(self.detect(window))
        
        return pd.Series(regimes, index=data.index)


def detect_regime(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    ma_period: int = 50,
    adx_period: int = 14,
    ma_slope_threshold: float = 0.001,
    adx_threshold: float = 25,
) -> MarketRegime:
    """
    快速检测单次市场状态
    
    Args:
        close: 收盘价序列
        high: 最高价序列
        low: 最低价序列
        ma_period: MA 周期
        adx_period: ADX 周期
        ma_slope_threshold: MA 斜率阈值
        adx_threshold: ADX 阈值
        
    Returns:
        MarketRegime
    """
    data = pd.DataFrame({
        'close': close,
        'high': high,
        'low': low,
    })
    
    config = RegimeConfig(
        ma_slope_threshold=ma_slope_threshold,
        adx_threshold=adx_threshold,
    )
    
    detector = RegimeDetector(config)
    return detector.detect(data)
