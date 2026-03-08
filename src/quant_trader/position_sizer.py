"""
仓位管理器

根据信号、账户情况计算仓位
"""
from __future__ import annotations
import logging
from typing import Optional
from dataclasses import dataclass

from .market_regime import Regime

logger = logging.getLogger("quant_trader.position_sizer")


@dataclass
class PositionSize:
    """仓位建议"""
    shares: int          # 股数
    value: float        # 金额
    ratio: float        # 占总资产比例
    reason: str         # 理由


class PositionSizer:
    """
    仓位管理器
    
    根据账户情况、信号置信度、市场环境计算仓位
    """
    
    def __init__(
        self,
        max_position_ratio: float = 0.10,   # 单笔最大仓位 10%
        min_position_ratio: float = 0.02,    # 单笔最小仓位 2%
    ):
        self.max_position_ratio = max_position_ratio
        self.min_position_ratio = min_position_ratio
    
    def calculate(
        self,
        ticker: str,
        price: float,
        total_assets: float,
        cash: float,
        signal_confidence: float,
        market_regime: Regime = Regime.RANGING,
        current_position: float = 0,
    ) -> PositionSize:
        """
        计算仓位
        
        Args:
            ticker: 股票代码
            price: 当前价格
            total_assets: 总资产
            cash: 实际可用现金
            signal_confidence: 信号置信度 0-1
            market_regime: 市场环境 (Regime 枚举)
            current_position: 当前持仓金额
            
        Returns:
            PositionSize
        """
        # 基础仓位 = 置信度 * 最大仓位
        base_ratio = signal_confidence * self.max_position_ratio
        
        # 根据市场环境调整
        if market_regime == Regime.TRENDING_UP:
            ratio = min(base_ratio * 1.2, self.max_position_ratio)
        elif market_regime == Regime.TRENDING_DOWN:
            ratio = base_ratio * 0.5
        else:  # RANGING
            ratio = base_ratio
        
        # 确保最小仓位
        ratio = max(ratio, self.min_position_ratio)
        
        # 用 cash 控制上限，留 5% buffer
        position_value = min(total_assets * ratio, cash * 0.95)
        
        # 计算股数 (取整百)
        shares = int(position_value / price / 100) * 100
        
        # 金额兜底 (一手成本)
        if shares == 0:
            lot_cost = 100 * price
            min_value = total_assets * self.min_position_ratio
            if lot_cost <= min_value and lot_cost <= cash * 0.95:
                shares = 100
            else:
                logger.info(f"{ticker} 一手成本 {lot_cost:.0f} 超过最小仓位 {min_value:.0f}，跳过建仓")
                shares = 0
        
        final_value = shares * price
        final_ratio = final_value / total_assets
        
        return PositionSize(
            shares=shares,
            value=final_value,
            ratio=final_ratio,
            reason=self._build_reason(signal_confidence, market_regime, ratio)
        )
    
    def _build_reason(self, confidence: float, regime: Regime, ratio: float) -> str:
        """构建理由"""
        conf_str = f"置信度{confidence:.0%}"
        
        regime_str = {
            Regime.TRENDING_UP: "趋势上涨",
            Regime.TRENDING_DOWN: "趋势下跌",
            Regime.RANGING: "震荡市",
        }.get(regime, "未知")
        
        return f"{conf_str}，{regime_str}，仓位{ratio:.1%}"


# 全局实例
_position_sizer: Optional[PositionSizer] = None


def get_position_sizer() -> PositionSizer:
    """获取全局仓位管理器实例"""
    global _position_sizer
    if _position_sizer is None:
        _position_sizer = PositionSizer()
    return _position_sizer
