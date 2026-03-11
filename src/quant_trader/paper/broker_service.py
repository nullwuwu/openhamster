"""
券商集成服务

在 PaperTradingService 基础上增加券商对接
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Union, List

from .service import PaperTradingService
from ..broker import BaseBroker, OrderStateMachine, Reconciler

logger = logging.getLogger("quant_trader.paper")


class BrokerTradingService(PaperTradingService):
    """券商交易服务"""
    
    def __init__(
        self,
        strategy,
        symbol: str = "2800.HK",
        db_path: str | None = None,
        initial_capital: float = 1_000_000,
        provider_name: str = "akshare",
        notifier=None,
        risk_manager=None,
        broker: Optional[BaseBroker] = None,
    ):
        """
        初始化
        
        Args:
            broker: 券商接口 (None=本地模拟)
        """
        super().__init__(
            strategy=strategy,
            symbol=symbol,
            db_path=db_path,
            initial_capital=initial_capital,
            provider_name=provider_name,
            notifier=notifier,
            risk_manager=risk_manager,
        )
        
        self.broker = broker
        self.state_machine = None
        self.reconciler = None
        
        # 如果有券商，创建状态机和对账器
        if self.broker:
            if hasattr(self.broker, 'mode') and self.broker.mode == "live":
                if getattr(self.broker, 'require_confirm_live', True):
                    logger.warning("⚠️" + "="*50)
                    logger.warning("⚠️ WARNING: Broker mode is LIVE!")
                    logger.warning("⚠️ Real orders will be placed!")
                    logger.warning("⚠️" + "="*50)
        if self.broker:
            self.state_machine = OrderStateMachine(self.broker)
            self.reconciler = Reconciler(self.db)
    
    def bootstrap(self):
        """初始化（包括券商连接）"""
        # 父类初始化
        super().bootstrap()
        
        # 券商连接
        if self.broker:
            logger.info("🔌 连接券商...")
            if self.broker.connect():
                logger.info("✅ 券商已连接")
                
                # 对账
                self._reconcile()
            else:
                logger.warning("⚠️ 券商连接失败，回退到本地模拟")
                self.broker = None
    
    def _reconcile(self):
        """对账"""
        if not self.reconciler:
            return
        
        try:
            # 获取券商持仓
            broker_positions = self.broker.get_positions()
            
            # 获取本地持仓
            local_positions = []
            for symbol, pos in self.account.positions.items():
                local_positions.append({
                    "symbol": symbol,
                    "qty": pos["quantity"],
                })
            
            # 对账
            result = self.reconciler.run(broker_positions, local_positions)
            
            if result["status"] == "MISMATCH":
                # 告警
                logger.error(f"⚠️ 对账不一致: {result['details']}")
                
        except Exception as e:
            logger.warning(f"⚠️ 对账失败: {e}")
    
    def _check_idempotency(self, run_id: str) -> bool:
        """
        检查幂等性
        
        Args:
            run_id: 唯一运行ID
            
        Returns:
            bool: True=可以执行, False=跳过
        """
        from ..storage import OrderRepository
        
        # 查询该 run_id 是否已有成功订单
        order_repo = OrderRepository(self.db)
        orders = order_repo.get_all(limit=100)
        
        for order in orders:
            if order.status == "FILLED" and order.symbol == self.symbol:
                # 已有成功订单，认为已执行
                logger.warning(f"⚠️ 幂等拦截: {run_id} 已有成功订单，跳过")
                return False
        
        return True
    
    def run_once(self, date: Optional[str] = None) -> bool:
        """
        执行一次交易（带券商支持）
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        # 生成唯一 run_id
        run_id = f"{date}_{self.symbol}"
        
        logger.info(f"=== 开始执行: {date} ({run_id}) ===")
        
        # 1. 幂等检查
        if not self._check_idempotency(run_id):
            logger.info(f"⏭️ {run_id} 已执行，跳过")
            return True
        
        # 2. 检查今天是否已执行
        from ..storage import DailyNavRepository
        nav_repo = DailyNavRepository(self.db)
        
        if nav_repo.exists(date):
            logger.info(f"⏭️ {date} 已执行，跳过")
            return True
        
        # 3. 拉取数据
        data = self._fetch_data()
        
        if data.empty:
            logger.warning("⚠️ 无数据")
            return False
        
        # 4. 获取最新价格
        latest_price = data["close"].iloc[-1]
        trade_date = data.index[-1].strftime("%Y-%m-%d")
        
        logger.info(f"📊 数据: {len(data)} 条, 最新价: {latest_price:.2f}")
        
        # 5. 生成信号
        signal = self.strategy.generate_signal(data)
        
        logger.info(f"📈 原始信号: {signal}")
        
        # 6. 风控评估
        from ..strategy.signals import Signal
        if self.risk_manager and signal != Signal.HOLD:
            position = self.account.get_position(self.symbol)
            position_qty = position["quantity"] if position else 0
            avg_cost = position["avg_cost"] if position else 0
            
            navs = nav_repo.get_all(30)
            if navs:
                equity_values = [n.total_equity for n in navs]
                equity_values.append(self.account.total_equity({self.symbol: latest_price}))
                cummax = max(equity_values)
                max_dd = (min(equity_values) - cummax) / cummax if cummax > 0 else 0
            else:
                max_dd = 0
            
            context = {
                "position_qty": position_qty,
                "avg_cost": avg_cost,
                "current_price": latest_price,
                "total_equity": self.account.total_equity({self.symbol: latest_price}),
                "cash": self.account.cash,
                "max_drawdown_pct": max_dd,
            }
            
            original_signal = signal
            signal = self.risk_manager.evaluate(signal, context)
            
            if original_signal != signal:
                logger.warning(f"⚠️ 风控干预: {original_signal} -> {signal}")
        
        logger.info(f"📈 最终信号: {signal}")
        
        # 7. 执行交易
        action = "HOLD"
        
        if signal == Signal.HOLD:
            pass
        
        elif self.broker:
            # 券商模式
            action = self._execute_broker_order(signal, latest_price, trade_date)
        
        else:
            # 本地模拟模式
            action = self._execute_paper_order(signal, latest_price, trade_date)
        
        # 8. 保存状态
        price_map = {self.symbol: latest_price}
        self.executor.save_state(price_map, trade_date)
        
        # 9. 打印账户摘要
        total_equity = self.account.total_equity(price_map)
        position = self.account.get_position(self.symbol)
        position_info = f"{position['quantity']} 股 @ {position['avg_cost']:.2f}" if position else "空仓"
        
        logger.info(f"""
=== 账户摘要 ===
日期: {trade_date}
信号: {signal.value} ({action})
持仓: {position_info}
现金: {self.account.cash:,.2f}
总权益: {total_equity:,.2f}
""")
        
        # 10. 发送通知
        self._send_notification(
            trade_date=trade_date,
            signal=signal.value,
            action=action,
            latest_price=latest_price,
            total_equity=total_equity,
        )
        
        return True
    
    def _execute_broker_order(self, signal, price, date) -> str:
        """执行券商订单"""
        from ..strategy.signals import Signal
        
        if signal == Signal.BUY:
            # 检查是否已有持仓
            if self.account.get_position(self.symbol):
                logger.info("已有持仓，跳过买入")
                return "HOLD"
            
            # 计算买入数量
            qty = int(self.account.cash * 0.95 / price)
            
            if qty <= 0:
                logger.warning("现金不足")
                return "HOLD"
            
            # 下单
            order_id = self.broker.place_order(
                symbol=self.symbol,
                side="BUY",
                qty=qty,
                price=price,
            )
            
            # 等待成交
            if self.state_machine:
                final_state = self.state_machine.wait_for_final(order_id)
                logger.info(f"订单终态: {final_state}")
            
            # 更新本地状态
            self.account.buy(self.symbol, price, qty)
            
            return "BUY"
        
        elif signal == Signal.SELL:
            position = self.account.get_position(self.symbol)
            if not position:
                logger.info("无持仓，跳过卖出")
                return "HOLD"
            
            qty = position["quantity"]
            
            # 下单
            order_id = self.broker.place_order(
                symbol=self.symbol,
                side="SELL",
                qty=qty,
                price=price,
            )
            
            # 等待成交
            if self.state_machine:
                final_state = self.state_machine.wait_for_final(order_id)
                logger.info(f"订单终态: {final_state}")
            
            # 更新本地状态
            self.account.sell(self.symbol, price, qty)
            
            return "SELL"
        
        return "HOLD"
    
    def _execute_paper_order(self, signal, price, date) -> str:
        """执行本地模拟订单"""
        from ..strategy.signals import Signal
        
        if signal == Signal.BUY:
            if self.account.get_position(self.symbol):
                logger.info("已有持仓，跳过买入")
            else:
                success = self.executor.execute_signal(self.symbol, signal, price, date)
                return "BUY" if success else "HOLD"
        
        elif signal == Signal.SELL:
            if not self.account.get_position(self.symbol):
                logger.info("无持仓，跳过卖出")
            else:
                success = self.executor.execute_signal(self.symbol, signal, price, date)
                return "SELL" if success else "HOLD"
        
        return "HOLD"
    
    def close(self):
        """关闭连接"""
        if self.broker:
            self.broker.disconnect()
        
        if self.db:
            self.db.close()
