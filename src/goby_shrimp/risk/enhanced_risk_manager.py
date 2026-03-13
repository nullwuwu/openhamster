"""
增强风控模块

包含止损、仓位管理、风险监控等
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime

from ..strategy.signals import Signal

logger = logging.getLogger("goby_shrimp.risk")


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    qty: float = 0
    avg_cost: float = 0
    entry_date: Optional[str] = None
    
    @property
    def market_value(self) -> float:
        return self.qty * self.avg_cost
    
    def update_pnl(self, current_price: float) -> Dict[str, float]:
        """计算盈亏"""
        if self.qty == 0:
            return {"pnl": 0, "pnl_pct": 0}
        pnl = (current_price - self.avg_cost) * self.qty
        pnl_pct = (current_price - self.avg_cost) / self.avg_cost if self.avg_cost > 0 else 0
        return {"pnl": pnl, "pnl_pct": pnl_pct}


@dataclass
class RiskState:
    """风控状态"""
    total_equity: float = 100000  # 总权益
    cash: float = 100000  # 现金
    positions: Dict[str, Position] = field(default_factory=dict)
    daily_pnl: float = 0
    total_pnl: float = 0
    
    @property
    def total_position_value(self) -> float:
        return sum(p.market_value for p in self.positions.values())
    
    @property
    def total_value(self) -> float:
        return self.cash + self.total_position_value


class EnhancedRiskManager:
    """增强风控管理器"""
    
    def __init__(
        self,
        # 仓位管理
        max_position_pct: float = 0.6,  # 单标最大仓位
        max_total_position_pct: float = 0.9,  # 总仓位上限
        min_cash_reserve_pct: float = 0.1,  # 最小现金储备
        
        # 止损止盈
        stop_loss_pct: float = 0.08,  # 止损比例
        take_profit_pct: float = 0.20,  # 止盈比例
        trailing_stop_pct: float = 0.05,  # 追踪止损
        
        # 风险限制
        max_drawdown_pct: float = 0.15,  # 最大回撤限制
        max_daily_loss_pct: float = 0.05,  # 单日最大亏损
        max_trades_per_day: int = 3,  # 每日最大交易次数
        
        # 波动率风控
        use_volatility_stop: bool = True,
        volatility_period: int = 20,
        volatility_stop_multiplier: float = 2.0,  # N倍ATR止损
    ):
        """初始化"""
        # 仓位管理
        self.max_position_pct = max_position_pct
        self.max_total_position_pct = max_total_position_pct
        self.min_cash_reserve_pct = min_cash_reserve_pct
        
        # 止损止盈
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct
        
        # 风险限制
        self.max_drawdown_pct = max_drawdown_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_trades_per_day = max_trades_per_day
        
        # 波动率风控
        self.use_volatility_stop = use_volatility_stop
        self.volatility_period = volatility_period
        self.volatility_stop_multiplier = volatility_stop_multiplier
        
        # 状态
        self._state = RiskState()
        self._trades_today = 0
        self._last_trade_date: Optional[str] = None
        self._peak_equity: float = 100000
        self._high_prices: Dict[str, float] = {}  # 追踪最高价
    
    @property
    def state(self) -> RiskState:
        return self._state
    
    def update_state(
        self,
        total_equity: float = None,
        cash: float = None,
        positions: Dict[str, Position] = None,
        daily_pnl: float = None,
    ) -> None:
        """更新状态"""
        if total_equity is not None:
            self._state.total_equity = total_equity
            # 更新峰值
            if total_equity > self._peak_equity:
                self._peak_equity = total_equity
        
        if cash is not None:
            self._state.cash = cash
        
        if positions is not None:
            self._state.positions = positions
        
        if daily_pnl is not None:
            self._state.daily_pnl = daily_pnl
            self._state.total_pnl = total_equity - 100000 if total_equity else 0
        
        # 检查是否新的一天
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_trade_date != today:
            self._trades_today = 0
            self._last_trade_date = today
    
    def evaluate(
        self,
        signal: Signal,
        symbol: str,
        current_price: float,
    ) -> Signal:
        """
        评估信号
        
        Args:
            signal: 原始信号
            symbol: 股票代码
            current_price: 当前价格
            
        Returns:
            Signal: 处理后的信号
        """
        position = self._state.positions.get(symbol)
        
        # 1. 检查是否新的一天，重置交易计数
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_trade_date != today:
            self._trades_today = 0
            self._last_trade_date = today
        
        # 2. 检查每日交易次数限制
        if self._trades_today >= self.max_trades_per_day:
            logger.warning(f"⚠️ 今日交易次数已达上限 ({self.max_trades_per_day})")
            if signal == Signal.BUY:
                return Signal.HOLD
        
        # 3. 检查总仓位上限
        if signal == Signal.BUY:
            current_position_value = position.market_value if position else 0
            new_position_value = current_position_value + current_price * 100  # 假设买100股
            total_position_pct = (self._state.total_position_value + new_position_value) / self._state.total_value
            
            if total_position_pct > self.max_total_position_pct:
                logger.warning(f"⚠️ 总仓位超限: {total_position_pct*100:.1f}%")
                return Signal.HOLD
            
            # 检查现金储备
            available_cash = self._state.cash
            if available_cash / self._state.total_value < self.min_cash_reserve_pct:
                logger.warning(f"⚠️ 现金储备不足")
                return Signal.HOLD
        
        # 4. 有持仓时的风控检查
        if position and position.qty > 0:
            pnl_info = position.update_pnl(current_price)
            pnl_pct = pnl_info["pnl_pct"]
            
            # 更新最高价 (用于追踪止损)
            if symbol not in self._high_prices or current_price > self._high_prices[symbol]:
                self._high_prices[symbol] = current_price
            
            # 4a. 追踪止损
            if self.trailing_stop_pct > 0:
                high_price = self._high_prices.get(symbol, current_price)
                trailing_stop_price = high_price * (1 - self.trailing_stop_pct)
                
                if current_price < trailing_stop_price:
                    logger.warning(f"⚠️ 追踪止损触发: {current_price:.2f} < {trailing_stop_price:.2f}")
                    self._trades_today += 1
                    return Signal.SELL
            
            # 4b. 固定止损
            if pnl_pct <= -self.stop_loss_pct:
                logger.warning(f"⚠️ 止损触发: 亏损 {pnl_pct*100:.2f}%")
                self._trades_today += 1
                return Signal.SELL
            
            # 4c. 止盈
            if pnl_pct >= self.take_profit_pct:
                logger.warning(f"⚠️ 止盈触发: 盈利 {pnl_pct*100:.2f}%")
                self._trades_today += 1
                return Signal.SELL
        
        # 5. 账户回撤超限
        current_drawdown = (self._peak_equity - self._state.total_equity) / self._peak_equity
        if current_drawdown >= self.max_drawdown_pct:
            logger.warning(f"⚠️ 账户回撤超限: {current_drawdown*100:.2f}%")
            if signal == Signal.BUY:
                return Signal.HOLD
        
        # 6. 单日亏损超限
        daily_loss_pct = -self._state.daily_pnl / self._state.total_equity
        if daily_loss_pct >= self.max_daily_loss_pct:
            logger.warning(f"⚠️ 单日亏损超限: {daily_loss_pct*100:.2f}%")
            if signal == Signal.BUY:
                return Signal.HOLD
        
        # 7. 已有持仓时不允许买入（单标限制）
        if signal == Signal.BUY and position and position.qty > 0:
            logger.info(f"⚠️ 已有 {symbol} 持仓，买入改为 HOLD")
            return Signal.HOLD
        
        # 8. 空仓时不允许卖出
        if signal == Signal.SELL and (not position or position.qty == 0):
            return Signal.HOLD
        
        # 更新交易计数
        if signal in [Signal.BUY, Signal.SELL]:
            self._trades_today += 1
        
        return signal
    
    def get_position_size(
        self,
        symbol: str,
        current_price: float,
        signal: Signal,
    ) -> float:
        """
        计算买入数量
        
        Args:
            symbol: 股票代码
            current_price: 当前价格
            signal: 信号
            
        Returns:
            float: 建议买入数量
        """
        if signal != Signal.BUY:
            return 0
        
        # 基于总权益和仓位限制计算
        max_value = self._state.total_value * self.max_position_pct
        available_cash = self._state.cash * (1 - self.min_cash_reserve_pct)
        
        # 取较小值
        max_buy_value = min(max_value, available_cash)
        
        # 计算股数
        qty = int(max_buy_value / current_price / 100) * 100  # 整手
        
        return max(qty, 0)
    
    def to_dict(self) -> dict:
        """转换为配置字典"""
        return {
            "max_position_pct": self.max_position_pct,
            "max_total_position_pct": self.max_total_position_pct,
            "min_cash_reserve_pct": self.min_cash_reserve_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "trailing_stop_pct": self.trailing_stop_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_trades_per_day": self.max_trades_per_day,
        }
    
    @classmethod
    def from_dict(cls, config: dict) -> "EnhancedRiskManager":
        """从配置字典创建"""
        return cls(**config)


# 兼容性别名
RiskManager = EnhancedRiskManager
