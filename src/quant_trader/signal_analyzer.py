"""
交易信号分析器

为 Agent 提供技术分析和信号生成能力
"""
from __future__ import annotations
import logging
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from quant_trader.strategy.signals import Signal

logger = logging.getLogger("quant_trader.signal_analyzer")


@dataclass
class SignalResult:
    """信号结果"""
    signal: Signal
    confidence: float  # 0-1
    reason: str
    indicators: dict


class SignalAnalyzer:
    """
    信号分析器
    
    基于技术指标生成交易信号
    """
    
    def __init__(self):
        pass
    
    def analyze(
        self,
        ticker: str,
        ohlcv: dict,
    ) -> Optional[SignalResult]:
        """
        分析并生成信号
        
        Args:
            ticker: 股票代码
            ohlcv: K线数据 (from get_ohlcv)
            
        Returns:
            SignalResult or None
            
        TODO:
        - high / low / volume 用于未来增强分析
        - 成交量信号
        - 布林带
        - 形态识别
        """
        if ohlcv is None or len(ohlcv.get("close", [])) < 30:
            logger.warning(f"数据不足: {ticker}")
            return None
        
        close = ohlcv["close"]
        
        # TODO: high = ohlcv.get("high", [])
        # TODO: low = ohlcv.get("low", [])
        # TODO: volume = ohlcv.get("volume", [])
        
        # 计算指标
        ma5 = self._ma(close, 5)
        ma20 = self._ma(close, 20)
        
        # MA 序列 (用于交叉判断)
        ma5_series = [self._ma(close[:i+1], 5) for i in range(len(close)-5, len(close))]
        ma20_series = [self._ma(close[:i+1], 20) for i in range(len(close)-20, len(close))]
        
        rsi = self._rsi(close, 14)
        
        # 完整 MACD 序列
        macd_line, signal_line, histogram, macd_series = self._macd(close)
        
        # 生成信号
        signals = []
        
        # 1. MA 交叉信号 (前后对比)
        ma_cross = self._ma_cross_signal(ma5_series, ma20_series)
        if ma_cross:
            signals.append(ma_cross)
        
        # 2. RSI 超买超卖
        rsi_result = self._rsi_signal(rsi)
        if rsi_result:
            signals.append(rsi_result)
        
        # 3. MACD 信号 (检测 histogram 变号)
        macd_result = self._macd_signal(macd_series)
        if macd_result:
            signals.append(macd_result)
        
        # 综合判断
        return self._combine_signals(ticker, signals, {
            "ma5": ma5,
            "ma20": ma20,
            "rsi": rsi,
            "macd": macd_line,
            "macd_signal": signal_line,
            "macd_hist": histogram,
        })
    
    def _ma(self, data: list, period: int) -> float:
        """简单移动平均"""
        if len(data) < period:
            return data[-1] if data else 0
        return sum(data[-period:]) / period
    
    def _rsi(self, data: list, period: int = 14) -> float:
        """RSI 指标"""
        if len(data) < period + 1:
            return 50.0
        
        deltas = [data[i] - data[i-1] for i in range(1, len(data))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _ema(self, data: list, period: int) -> float:
        """
        指数移动平均 - 真正的 EMA 递推
        
        EMA_t = Price_t * k + EMA_{t-1} * (1 - k)
        其中 k = 2 / (period + 1)
        """
        if len(data) < period:
            return data[-1] if data else 0
        
        k = 2 / (period + 1)
        
        # 先计算第一个 SMA 作为起点
        ema = sum(data[:period]) / period
        
        # 递推计算
        for price in data[period:]:
            ema = price * k + ema * (1 - k)
        
        return ema
    
    def _macd(self, data: list, fast: int = 12, slow: int = 26, signal: int = 9):
        """
        MACD 指标 - 完整计算
        
        Returns:
            (macd_line, signal_line, histogram, macd_series)
            - macd_series 是对齐后的完整序列，用于检测变号
        """
        if len(data) < slow:
            return 0, 0, 0, []
        
        # 计算 EMA 序列
        ema_fast_series = []
        ema_slow_series = []
        
        k_fast = 2 / (fast + 1)
        k_slow = 2 / (slow + 1)
        
        # 初始化
        ema_fast = sum(data[:fast]) / fast
        ema_slow = sum(data[:slow]) / slow
        
        # 递推 - 保留完整序列
        for i in range(fast, len(data)):
            ema_fast = data[i] * k_fast + ema_fast * (1 - k_fast)
            ema_fast_series.append(ema_fast)
        
        for i in range(slow, len(data)):
            ema_slow = data[i] * k_slow + ema_slow * (1 - k_slow)
            ema_slow_series.append(ema_slow)
        
        # MACD line = EMA_fast - EMA_slow
        # 需要对齐: 从 slow 开始 (因为 EMA_slow 从 index=slow 开始有效)
        offset = slow - fast  # offset = 14
        
        if offset > 0:
            # fast 更短，取后面的部分
            ema_fast_aligned = ema_fast_series[offset:]
        else:
            ema_fast_aligned = ema_fast_series
        
        # 对齐后的 MACD 序列
        macd_series = []
        for i in range(len(ema_slow_series)):
            if i < len(ema_fast_aligned):
                macd_series.append(ema_fast_aligned[i] - ema_slow_series[i])
        
        if not macd_series:
            return 0, 0, 0, []
        
        macd_line = macd_series[-1]
        
        # Signal line = EMA(MACD, 9)
        k_sig = 2 / (signal + 1)
        sig_line = sum(macd_series[:signal]) / signal
        for val in macd_series[signal:]:
            sig_line = val * k_sig + sig_line * (1 - k_sig)
        
        histogram = macd_line - sig_line
        
        return macd_line, sig_line, histogram, macd_series
    
    def _ma_cross_signal(self, ma5_recent: list, ma20_recent: list) -> Optional[dict]:
        """
        MA 交叉信号 - 对比前后两根 K 线
        
        Args:
            ma5_recent: 最近几根 MA5 值 (至少2个)
            ma20_recent: 最近几根 MA20 值 (至少2个)
        """
        if len(ma5_recent) < 2 or len(ma20_recent) < 2:
            return None
        
        # 取最近两根对比
        ma5_prev = ma5_recent[-2]
        ma5_curr = ma5_recent[-1]
        ma20_prev = ma20_recent[-2]
        ma20_curr = ma20_recent[-1]
        
        # 金叉: MA5 从下往上穿过 MA20
        if ma5_prev <= ma20_prev and ma5_curr > ma20_curr:
            return {"type": "MA_CROSS", "direction": Signal.BUY, "confidence": 0.7, "reason": "MA5金叉MA20"}
        
        # 死叉: MA5 从上往下穿过 MA20
        elif ma5_prev >= ma20_prev and ma5_curr < ma20_curr:
            return {"type": "MA_CROSS", "direction": Signal.SELL, "confidence": 0.7, "reason": "MA5死叉MA20"}
        
        return None
    
    def _rsi_signal(self, rsi: float) -> Optional[dict]:
        """RSI 超买超卖信号"""
        if rsi < 30:
            return {"type": "RSI", "direction": Signal.BUY, "confidence": 0.6, "reason": f"RSI超卖({rsi:.0f})"}
        elif rsi > 70:
            return {"type": "RSI", "direction": Signal.SELL, "confidence": 0.6, "reason": f"RSI超买({rsi:.0f})"}
        return None
    
    def _macd_signal(self, macd_series: list) -> Optional[dict]:
        """
        MACD 信号 - 检测 histogram 变号
        
        检测 MACD histogram 从负变正(金叉) 或从正变负(死叉)
        """
        if len(macd_series) < 2:
            return None
        
        # 计算 histogram 序列
        signal_period = 9
        if len(macd_series) < signal_period:
            return None
        
        # Signal line
        k_sig = 2 / (signal_period + 1)
        sig_line = sum(macd_series[:signal_period]) / signal_period
        hist_series = []
        
        for i, val in enumerate(macd_series[signal_period:], signal_period):
            sig_line = val * k_sig + sig_line * (1 - k_sig)
            hist_series.append(val - sig_line)
        
        if len(hist_series) < 2:
            return None
        
        # 检测变号
        hist_prev = hist_series[-2]
        hist_curr = hist_series[-1]
        
        if hist_prev <= 0 and hist_curr > 0:
            return {"type": "MACD", "direction": Signal.BUY, "confidence": 0.7, "reason": "MACD金叉(histogram变号)"}
        elif hist_prev >= 0 and hist_curr < 0:
            return {"type": "MACD", "direction": Signal.SELL, "confidence": 0.7, "reason": "MACD死叉(histogram变号)"}
        
        return None
    
    def _combine_signals(self, ticker: str, signals: list, indicators: dict) -> SignalResult:
        """综合多个信号"""
        if not signals:
            return SignalResult(
                signal=Signal.HOLD,
                confidence=0.5,
                reason="无明确信号",
                indicators=indicators,
            )
        
        # 统计信号
        buy_count = sum(1 for s in signals if s["direction"] == Signal.BUY)
        sell_count = sum(1 for s in signals if s["direction"] == Signal.SELL)
        
        total = len(signals)
        
        if buy_count > sell_count and buy_count >= total * 0.6:
            confidence = buy_count / 3
            reason = f"买入信号({buy_count}/{total}): " + "; ".join([s["reason"] for s in signals if s["direction"] == Signal.BUY])
            return SignalResult(
                signal=Signal.BUY,
                confidence=confidence,
                reason=reason,
                indicators=indicators,
            )
        elif sell_count > buy_count and sell_count >= total * 0.6:
            confidence = sell_count / 3
            reason = f"卖出信号({sell_count}/{total}): " + "; ".join([s["reason"] for s in signals if s["direction"] == Signal.SELL])
            return SignalResult(
                signal=Signal.SELL,
                confidence=confidence,
                reason=reason,
                indicators=indicators,
            )
        
        return SignalResult(
            signal=Signal.HOLD,
            confidence=0.5,
            reason=f"信号分歧({buy_count}买/{sell_count}卖)，保持观望",
            indicators=indicators,
        )


# 全局实例
_signal_analyzer: Optional[SignalAnalyzer] = None


def get_signal_analyzer() -> SignalAnalyzer:
    """获取全局信号分析器实例"""
    global _signal_analyzer
    if _signal_analyzer is None:
        _signal_analyzer = SignalAnalyzer()
    return _signal_analyzer
