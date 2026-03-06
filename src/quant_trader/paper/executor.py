"""
模拟盘执行器

执行交易信号，写入数据库
"""
import logging
from datetime import datetime
from typing import Dict

from ..storage import (
    Database,
    AccountRepository,
    PositionRepository,
    OrderRepository,
    DailyNavRepository,
    Order,
    DailyNav,
)
from ..strategy.signals import Signal
from .account import PaperAccount

logger = logging.getLogger("quant_trader.paper")


class PaperExecutor:
    """模拟盘执行器"""
    
    def __init__(
        self,
        db: Database,
        account: PaperAccount,
        commission_rate: float = 0.001,
    ):
        """
        初始化
        
        Args:
            db: 数据库实例
            account: 账户
            commission_rate: 手续费率
        """
        self.db = db
        self.account = account
        self.commission_rate = commission_rate
        
        # 仓库
        self.account_repo = AccountRepository(db)
        self.position_repo = PositionRepository(db)
        self.order_repo = OrderRepository(db)
        self.nav_repo = DailyNavRepository(db)
    
    def execute_signal(
        self,
        symbol: str,
        signal: Signal,
        price: float,
        date: str,
    ) -> bool:
        """
        执行信号
        
        Args:
            symbol: 股票代码
            signal: 信号
            price: 成交价格（收盘价）
            date: 交易日期
            
        Returns:
            bool: 是否执行成功
        """
        if signal == Signal.HOLD:
            return True
        
        if signal == Signal.BUY:
            return self._execute_buy(symbol, price)
        
        if signal == Signal.SELL:
            return self._execute_sell(symbol, price)
        
        return True
    
    def _execute_buy(self, symbol: str, price: float) -> bool:
        """执行买入"""
        # 计算可买入股数（预留手续费）
        available_cash = self.account.cash * (1 - self.commission_rate)
        quantity = int(available_cash / price)
        
        if quantity <= 0:
            logger.warning(f"现金不足，无法买入 {symbol}")
            return False
        
        # 执行买入
        success = self.account.buy(symbol, price, quantity)
        
        if success:
            # 写入订单
            order = Order(
                symbol=symbol,
                side="BUY",
                quantity=quantity,
                price=price,
                amount=price * quantity,
                status="FILLED",
            )
            self.order_repo.create(order)
        
        return success
    
    def _execute_sell(self, symbol: str, price: float) -> bool:
        """执行卖出"""
        position = self.account.get_position(symbol)
        
        if not position:
            logger.warning(f"无持仓可卖: {symbol}")
            return False
        
        # 全部卖出
        quantity = position["quantity"]
        
        # 执行卖出
        success = self.account.sell(symbol, price, quantity)
        
        if success:
            # 写入订单
            order = Order(
                symbol=symbol,
                side="SELL",
                quantity=quantity,
                price=price,
                amount=price * quantity,
                status="FILLED",
            )
            self.order_repo.create(order)
        
        return success
    
    def save_state(self, price_map: Dict[str, float], trade_date: str):
        """
        保存状态到数据库
        
        Args:
            price_map: 当前价格
            trade_date: 交易日期
        """
        # 更新账户
        total_equity = self.account.total_equity(price_map)
        account_model = self.account_repo.get()
        if account_model:
            account_model.cash = self.account.cash
            account_model.total_equity = total_equity
            self.account_repo.update(account_model)
        
        # 更新持仓
        for symbol, pos in self.account.positions.items():
            price = price_map.get(symbol, pos["avg_cost"])
            position = self.position_repo.get(symbol)
            if position is None:
                from ..storage.models import Position
                position = Position(symbol=symbol)
            
            position.quantity = pos["quantity"]
            position.avg_cost = pos["avg_cost"]
            position.market_value = pos["quantity"] * price
            self.position_repo.upsert(position)
        
        # 删除零持仓
        all_positions = self.position_repo.get_all()
        for pos in all_positions:
            if pos.symbol not in self.account.positions:
                self.position_repo.delete(pos.symbol)
        
        # 保存每日净值
        if not self.nav_repo.exists(trade_date):
            position_value = sum(
                pos["quantity"] * price_map.get(symbol, pos["avg_cost"])
                for symbol, pos in self.account.positions.items()
            )
            nav = DailyNav(
                trade_date=trade_date,
                cash=self.account.cash,
                position_value=position_value,
                total_equity=total_equity,
            )
            self.nav_repo.create(nav)
            logger.info(f"💾 净值快照: {trade_date}, {total_equity:.2f}")
    
    def load_state(self) -> bool:
        """
        从数据库加载状态
        
        Returns:
            bool: 是否成功加载
        """
        # 加载账户
        account_model = self.account_repo.get()
        if account_model:
            self.account.cash = account_model.cash
        
        # 加载持仓
        positions = self.position_repo.get_all()
        for pos in positions:
            if pos.quantity > 0:
                self.account.positions[pos.symbol] = {
                    "quantity": pos.quantity,
                    "avg_cost": pos.avg_cost,
                }
        
        return True
