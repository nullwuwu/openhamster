"""
风控管理器

评估交易信号，应用风控规则
"""
import logging
from typing import Optional

from ..strategy.signals import Signal

logger = logging.getLogger("openhamster.risk")


class RiskManager:
    """风控管理器"""
    
    def __init__(
        self,
        max_position_pct: float = 0.6,
        stop_loss_pct: float = 0.08,
        take_profit_pct: float = 0.20,
        max_drawdown_pct: float = 0.15,
    ):
        """
        初始化
        
        Args:
            max_position_pct: 单标的最大仓位占总权益比例
            stop_loss_pct: 止损比例 (0.08 = 8%)
            take_profit_pct: 止盈比例 (0.20 = 20%)
            max_drawdown_pct: 最大回撤限制
        """
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_drawdown_pct = max_drawdown_pct
    
    def evaluate(
        self,
        signal: Signal,
        context: dict,
    ) -> Signal:
        """
        评估信号
        
        Args:
            signal: 原始信号
            context: 上下文，包含:
                - position_qty: 持仓数量
                - avg_cost: 平均成本
                - current_price: 当前价格
                - total_equity: 总权益
                - cash: 现金
                - max_drawdown_pct: 当前回撤比例
                
        Returns:
            Signal: 处理后的信号
        """
        # 获取上下文
        position_qty = context.get("position_qty", 0)
        avg_cost = context.get("avg_cost", 0)
        current_price = context.get("current_price", 0)
        total_equity = context.get("total_equity", 0)
        max_drawdown_pct = context.get("max_drawdown_pct", 0)
        
        # 有持仓时的风控检查
        if position_qty > 0 and current_price > 0 and avg_cost > 0:
            # 计算持仓盈亏比例
            pnl_pct = (current_price - avg_cost) / avg_cost
            
            # 1. 止损检查
            if pnl_pct <= -self.stop_loss_pct:
                logger.warning(f"⚠️ 止损触发: 亏损 {pnl_pct*100:.2f}%, 强制 SELL")
                return Signal.SELL
            
            # 2. 止盈检查
            if pnl_pct >= self.take_profit_pct:
                logger.warning(f"⚠️ 止盈触发: 盈利 {pnl_pct*100:.2f}%, 强制 SELL")
                return Signal.SELL
        
        # 3. 账户回撤超限检查
        if max_drawdown_pct <= -self.max_drawdown_pct:
            logger.warning(f"⚠️ 账户回撤超限: {max_drawdown_pct*100:.2f}%, 暂停开仓")
            if signal == Signal.BUY:
                logger.warning("⚠️ 回撤超限，买入信号改为 HOLD")
                return Signal.HOLD
        
        # 4. 仓位超限检查
        if signal == Signal.BUY and total_equity > 0 and current_price > 0:
            # 计算如果买入后的仓位占比
            available_cash = context.get("cash", 0)
            potential_position = available_cash * 0.95 / current_price  # 预留手续费
            potential_value = potential_position * current_price
            potential_pct = potential_value / total_equity
            
            if potential_pct > self.max_position_pct:
                logger.warning(f"⚠️ 仓位超限: 计划仓位 {potential_pct*100:.2f}% > 上限 {self.max_position_pct*100:.2f}%, 买入改为 HOLD")
                return Signal.HOLD
        
        # 5. 已有持仓时不允许买入
        if signal == Signal.BUY and position_qty > 0:
            logger.info("⚠️ 已有持仓，买入信号改为 HOLD")
            return Signal.HOLD
        
        # 其他情况透传原始信号
        return signal
    
    def to_dict(self) -> dict:
        """转换为配置字典"""
        return {
            "max_position_pct": self.max_position_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
        }
