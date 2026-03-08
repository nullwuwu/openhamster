"""
风控管理器

交易前拦截 + 持仓中监控 + 强制止损止盈
"""
from __future__ import annotations
import logging
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from quant_trader.strategy.signals import Signal

logger = logging.getLogger("quant_trader.risk_manager")


class RiskAction(Enum):
    """风控动作"""
    PASS = "PASS"      # 放行
    REJECT = "REJECT"  # 拒绝交易
    REDUCE = "REDUCE"  # 缩减仓位
    FORCE_SELL = "FORCE_SELL"  # 强制卖出


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    action: RiskAction
    reason: str
    adjusted_shares: int = 0  # 缩仓后的股数
    adjusted_value: float = 0.0  # 缩仓后的金额


@dataclass
class PositionRisk:
    """持仓风控状态"""
    ticker: str
    entry_price: float
    current_price: float
    shares: int
    peak_price: float = 0.0  # 最高价 (用于移动止损)
    stop_loss_triggered: bool = False
    take_profit_triggered: bool = False


class RiskManager:
    """
    风控管理器
    
    交易前拦截 + 持仓中监控 + 强制止损止盈
    """
    
    def __init__(
        self,
        # 单日亏损熔断
        max_daily_loss_ratio: float = -0.03,  # -3%
        
        # 单股仓位上限
        max_single_position_ratio: float = 0.15,  # 15%
        
        # 总仓位上限
        max_total_position_ratio: float = 0.80,  # 80%
        
        # 现金保留比例
        min_cash_ratio: float = 0.05,  # 保留 5% 现金
        
        # 固定止损
        stop_loss_ratio: float = -0.08,  # -8%
        
        # 固定止盈
        take_profit_ratio: float = 0.15,  # 15%
        
        # 移动止损
        trailing_stop_ratio: float = 0.05,  # 从高点回撤 5%
    ):
        self.max_daily_loss_ratio = max_daily_loss_ratio
        self.max_single_position_ratio = max_single_position_ratio
        self.max_total_position_ratio = max_total_position_ratio
        self.min_cash_ratio = min_cash_ratio
        self.stop_loss_ratio = stop_loss_ratio
        self.take_profit_ratio = take_profit_ratio
        self.trailing_stop_ratio = trailing_stop_ratio
        
        # 每日开盘状态
        self._day_start_assets: float = 0.0
        self._day_pnl: float = 0.0
        
        # 持仓风控状态 (跨日保留)
        self._positions: dict[str, PositionRisk] = {}
    
    def reset_daily(self, day_start_assets: float):
        """
        每日开盘重置
        
        Args:
            day_start_assets: 开盘资产
        """
        self._day_start_assets = day_start_assets
        self._day_pnl = 0.0
        # Bug 1: 不清除持仓，保留隔夜持仓
        logger.info(f"📅 风控每日重置: 开盘资产={day_start_assets:,.0f}, 持仓数={len(self._positions)}")
    
    def pre_trade_check(
        self,
        ticker: str,
        shares: int,
        price: float,
        total_assets: float,
        cash: float,
        current_positions: dict[str, dict],
    ) -> RiskCheckResult:
        """
        交易前风控检查
        
        Args:
            ticker: 股票代码
            shares: 计划买入股数
            price: 当前价格
            total_assets: 总资产
            cash: 可用现金
            current_positions: 当前持仓 {ticker: {shares, price, value}}
            
        Returns:
            RiskCheckResult
        """
        order_value = shares * price
        
        # Bug 3: 单日亏损熔断 - 加 _day_start_assets > 0 保护
        if self._day_start_assets > 0 and self._day_pnl / self._day_start_assets <= self.max_daily_loss_ratio:
            logger.warning(f"🛡️ 风控拦截: 单日亏损 {self._day_pnl/self._day_start_assets:.1%} 触发熔断")
            return RiskCheckResult(
                action=RiskAction.REJECT,
                reason=f"单日亏损 {self._day_pnl/self._day_start_assets:.1%} >= {self.max_daily_loss_ratio:.1%}"
            )
        
        # Bug 4: 链式缩减 - 检查所有规则，返回最终的 REDUCE
        adjusted_shares = shares
        adjusted_value = order_value
        reject_reason = ""
        
        # ② 单股仓位上限
        current_position = current_positions.get(ticker, {})
        current_value = current_position.get("value", 0)
        new_value = current_value + adjusted_value
        if new_value / total_assets > self.max_single_position_ratio:
            max_value = total_assets * self.max_single_position_ratio
            allowed_value = max_value - current_value
            new_shares = int(allowed_value / price / 100) * 100
            if new_shares > 0:
                adjusted_shares = new_shares
                adjusted_value = new_shares * price
                logger.warning(f"🛡️ 风控缩仓: {ticker} 单股上限 {shares} -> {adjusted_shares}")
            else:
                reject_reason = f"单股仓位超限"
        
        # ③ 总仓位上限
        if not reject_reason:
            total_position_value = sum(p.get("value", 0) for p in current_positions.values()) + adjusted_value
            if total_position_value / total_assets > self.max_total_position_ratio:
                max_value = total_assets * self.max_total_position_ratio
                allowed_value = max_value - (total_position_value - adjusted_value)
                new_shares = int(allowed_value / price / 100) * 100
                if new_shares > 0:
                    adjusted_shares = new_shares
                    adjusted_value = new_shares * price
                    logger.warning(f"🛡️ 风控缩仓: {ticker} 总仓位上限 {shares} -> {adjusted_shares}")
                else:
                    reject_reason = f"总仓位超限"
        
        # ④ 现金不足
        if not reject_reason:
            max_spend = cash * (1 - self.min_cash_ratio)
            if adjusted_value > max_spend:
                new_shares = int(max_spend / price / 100) * 100
                if new_shares > 0:
                    adjusted_shares = new_shares
                    adjusted_value = new_shares * price
                    logger.warning(f"🛡️ 风控缩仓: {ticker} 现金不足 {shares} -> {adjusted_shares}")
                else:
                    reject_reason = f"现金不足"
        
        # 返回结果
        if reject_reason:
            return RiskCheckResult(
                action=RiskAction.REJECT,
                reason=reject_reason,
            )
        
        if adjusted_shares < shares:
            return RiskCheckResult(
                action=RiskAction.REDUCE,
                reason=f"缩仓: {shares} -> {adjusted_shares}",
                adjusted_shares=adjusted_shares,
                adjusted_value=adjusted_value,
            )
        
        # 全部通过
        return RiskCheckResult(
            action=RiskAction.PASS,
            reason="风控检查通过"
        )
    
    def register_position(
        self,
        ticker: str,
        shares: int,
        entry_price: float,
        current_price: float,
    ):
        """
        注册持仓 (买入后调用)
        
        Args:
            ticker: 股票代码
            shares: 股数
            entry_price: 入场价
            current_price: 当前价
        """
        self._positions[ticker] = PositionRisk(
            ticker=ticker,
            entry_price=entry_price,
            current_price=current_price,
            shares=shares,
            peak_price=current_price,  # 初始高点为当前价
        )
        logger.info(f"📝 注册持仓风控: {ticker} x {shares} @ {entry_price}")
    
    def update_position_price(self, ticker: str, current_price: float):
        """
        更新持仓现价 (用于移动止损)
        
        Args:
            ticker: 股票代码
            current_price: 当前价格
        """
        if ticker in self._positions:
            pos = self._positions[ticker]
            pos.current_price = current_price
            # 更新高点
            if current_price > pos.peak_price:
                pos.peak_price = current_price
    
    def evaluate(
        self,
        signal: str,
        context: dict,
    ) -> tuple[str, dict]:
        """
        风控评估 - 用于回测和实盘
        
        输入:
            signal: BUY / SELL / HOLD
            context: dict，包含:
                - ticker: 股票代码
                - price: 当前价格
                - date: 当前日期
                - cash: 可用现金
                - position: 当前持仓股数
                - total_assets: 总资产
                - current_positions: dict {ticker: {shares, price, value}}
                
        返回:
            (修正后的信号, 附加信息)
        """
        ticker = context.get("ticker", "")
        price = context.get("price", 0)
        date = context.get("date", "")
        cash = context.get("cash", 0)
        position = context.get("position", 0)
        total_assets = context.get("total_assets", 0)
        current_positions = context.get("current_positions", {})
        
        # 记录已处理的日期，避免重复 reset
        date_str = str(date)[:10]  # 只取日期部分
        if not hasattr(self, "_last_reset_date") or self._last_reset_date != date_str:
            self.reset_daily(total_assets)
            self._last_reset_date = date_str
        
        # 如果有持仓，更新价格
        if ticker in self._positions:
            self.update_position_price(ticker, price)
        
        # 检查止损止盈
        force_sell_tickers = []
        check_results = self.check_positions({ticker: price})
        for t, result in check_results:
            if result.action == RiskAction.FORCE_SELL:
                force_sell_tickers.append(t)
        
        # 如果触发强制卖出，返回 SELL
        if ticker in force_sell_tickers:
            # 记录已实现盈亏
            if position > 0 and price > 0:
                pnl = (price - context.get("avg_cost", price)) * position
                self.record_realized_pnl(pnl)
            self.remove_position(ticker)
            return Signal.SELL, None  # (signal, adjusted_shares)
        
        # 处理买入信号 - 统一使用字符串比较
        signal_val = signal.value if hasattr(signal, 'value') else str(signal)
        if signal_val == "BUY":  # BUY
            # 计算买入股数
            shares_to_buy = int(cash * 0.95 / price / 100) * 100
            
            check = self.pre_trade_check(
                ticker=ticker,
                shares=shares_to_buy,
                price=price,
                total_assets=total_assets,
                cash=cash,
                current_positions=current_positions,
            )
            
            if check.action == RiskAction.REJECT:
                logger.warning(f"🛡️ 风控拦截 BUY: {check.reason}")
                return Signal.HOLD, 0  # (signal, adjusted_shares)
            
            elif check.action == RiskAction.REDUCE:
                logger.warning(f"🛡️ 风控缩仓 BUY: {check.reason}, {check.adjusted_shares}股")
                # 注册持仓
                self.register_position(ticker, check.adjusted_shares, price, price)
                return Signal.BUY, check.adjusted_shares  # (signal, adjusted_shares)
            
            else:
                # 正常买入，注册持仓
                self.register_position(ticker, shares_to_buy, price, price)
                return Signal.BUY, shares_to_buy  # (signal, adjusted_shares)
        
        # 处理卖出信号
        elif signal_val == "SELL":  # SELL
            if position > 0:
                # 记录已实现盈亏
                avg_cost = context.get("avg_cost", price)
                pnl = (price - avg_cost) * position
                self.record_realized_pnl(pnl)
                self.remove_position(ticker)
            return Signal.SELL, None  # (signal, adjusted_shares)
        
        # HOLD
        return Signal.HOLD, 0  # (signal, adjusted_shares)
    
    def check_positions(
        self,
        current_prices: dict[str, float],
    ) -> list[tuple[str, RiskCheckResult]]:
        """
        检查所有持仓 (每日收盘调用)
        
        Args:
            current_prices: 当前价格 {ticker: price}
            
        Returns:
            需要强制卖出的列表 [(ticker, RiskCheckResult), ...]
        """
        results = []
        
        for ticker, pos in list(self._positions.items()):
            if ticker not in current_prices:
                continue
            
            current_price = current_prices[ticker]
            self.update_position_price(ticker, current_price)
            
            # 计算盈亏 (Bug fix: 加 entry_price 保护)
            if pos.entry_price > 0:
                pnl_ratio = (current_price - pos.entry_price) / pos.entry_price
            else:
                pnl_ratio = 0.0
            
            # ⑤ 固定止损
            if pnl_ratio <= self.stop_loss_ratio and not pos.stop_loss_triggered:
                logger.warning(f"🛑 强制止损: {ticker} 亏损 {pnl_ratio:.1%}")
                results.append((ticker, RiskCheckResult(
                    action=RiskAction.FORCE_SELL,
                    reason=f"固定止损: 亏损 {pnl_ratio:.1%}",
                    adjusted_shares=pos.shares,
                )))
                pos.stop_loss_triggered = True
                continue
            
        # ⑥ 固定止盈 (容差 0.001)
            if pnl_ratio >= self.take_profit_ratio - 0.001 and not pos.take_profit_triggered:
                logger.info(f"🛑 强制止盈: {ticker} 盈利 {pnl_ratio:.1%}")
                results.append((ticker, RiskCheckResult(
                    action=RiskAction.FORCE_SELL,
                    reason=f"固定止盈: 盈利 {pnl_ratio:.1%}",
                    adjusted_shares=pos.shares,
                )))
                pos.take_profit_triggered = True
                continue
            
            # ⑦ 移动止损 (盈利态从高点回撤)
            if pnl_ratio > 0 and pos.peak_price > 0:
                drawdown = (pos.peak_price - current_price) / pos.peak_price
                if drawdown >= self.trailing_stop_ratio:
                    logger.warning(f"🛑 移动止损: {ticker} 从高点回撤 {drawdown:.1%}")
                    results.append((ticker, RiskCheckResult(
                        action=RiskAction.FORCE_SELL,
                        reason=f"移动止损: 从高点回撤 {drawdown:.1%}",
                        adjusted_shares=pos.shares,
                    )))
                    continue
        
        return results
    
    def record_realized_pnl(self, pnl: float):
        """
        记录已实现盈亏
        
        Args:
            pnl: 盈亏金额 (正=盈利, 负=亏损)
        """
        self._day_pnl += pnl
        logger.info(f"📝 记录已实现盈亏: {pnl:+.0f}, 今日累计: {self._day_pnl:+.0f}")
    
    def remove_position(self, ticker: str):
        """
        移除持仓 (卖出后调用)
        
        Args:
            ticker: 股票代码
        """
        if ticker in self._positions:
            del self._positions[ticker]
            logger.info(f"🗑️ 移除持仓风控: {ticker}")
    
    def get_status(self) -> dict:
        """获取风控状态"""
        return {
            "day_start_assets": self._day_start_assets,
            "day_pnl": self._day_pnl,
            "positions": {
                ticker: {
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price,
                    "shares": pos.shares,
                    # Bug fix: entry_price 保护
                    "pnl_ratio": (pos.current_price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0.0,
                }
                for ticker, pos in self._positions.items()
            }
        }


# 全局实例
_risk_manager: Optional[RiskManager] = None


def get_risk_manager() -> RiskManager:
    """获取全局风控管理器实例"""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager
