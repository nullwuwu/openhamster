"""
模拟盘服务

核心业务逻辑：取数 → 信号 → 执行 → 持久化
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Union, List

import pandas as pd

from ..data import get_provider
from ..strategy import BaseStrategy
from ..storage import Database, init_db, DailyNavRepository
from .account import PaperAccount
from .executor import PaperExecutor
from ..strategy.signals import Signal
from ..notify import BaseNotifier, build_daily_report
from ..risk import RiskManager
from ..config import get_settings

logger = logging.getLogger("quant_trader.paper")


class PaperTradingService:
    """模拟盘服务"""
    
    def __init__(
        self,
        strategy: BaseStrategy,
        symbol: str = "2800.HK",
        db_path: str | None = None,
        initial_capital: float = 1_000_000,
        provider_name: str = "akshare",
        notifier: Optional[Union[BaseNotifier, List[BaseNotifier]]] = None,
        risk_manager: Optional[RiskManager] = None,
    ):
        """
        初始化
        
        Args:
            strategy: 交易策略
            symbol: 股票代码
            db_path: 数据库路径
            initial_capital: 初始资金
            provider_name: 数据源名称
            notifier: 通知器 (可选)
            risk_manager: 风控管理器 (可选)
        """
        self.strategy = strategy
        self.symbol = symbol
        settings = get_settings()
        self.db_path = db_path or settings.storage.paper_db_path
        self.initial_capital = initial_capital
        self.provider_name = provider_name
        self.notifier = notifier
        self.risk_manager = risk_manager
        
        # 初始化
        self.db: Optional[Database] = None
        self.account: Optional[PaperAccount] = None
        self.executor: Optional[PaperExecutor] = None
    
    def bootstrap(self):
        """初始化数据库和账户"""
        # 初始化数据库
        self.db = init_db(self.db_path)
        
        # 初始化账户
        from ..storage import AccountRepository
        account_repo = AccountRepository(self.db)
        account_model = account_repo.get_or_create(self.initial_capital)
        
        self.account = PaperAccount(
            initial_capital=self.initial_capital,
            cash=account_model.cash,
        )
        
        # 初始化执行器
        self.executor = PaperExecutor(
            db=self.db,
            account=self.account,
        )
        
        # 尝试加载已有状态
        self.load_state()
        
        logger.info(f"🚀 模拟盘启动: {self.symbol}, 初始资金: {self.initial_capital:,.0f}")
    
    def run_once(self, date: Optional[str] = None) -> bool:
        """
        执行一次交易
        
        Args:
            date: 交易日期 (YYYY-MM-DD), 默认今天
            
        Returns:
            bool: 是否成功执行
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"=== 开始执行: {date} ===")
        
        # 1. 检查今天是否已执行
        nav_repo = DailyNavRepository(self.db)
        if nav_repo.exists(date):
            logger.info(f"⏭️ {date} 已执行，跳过")
            return True
        
        # 2. 拉取数据（最近60天）
        data = self._fetch_data()
        
        if data.empty:
            logger.warning("⚠️ 无数据")
            return False
        
        # 3. 获取最新价格
        latest_price = data["close"].iloc[-1]
        trade_date = data.index[-1].strftime("%Y-%m-%d")
        
        logger.info(f"📊 数据: {len(data)} 条, 最新价: {latest_price:.2f}")
        
        # 4. 生成信号
        signal = self.strategy.generate_signal(data)
        
        logger.info(f"📈 原始信号: {signal}")
        
        # 5. 风控评估
        if self.risk_manager and signal != Signal.HOLD:
            position = self.account.get_position(self.symbol)
            position_qty = position["quantity"] if position else 0
            avg_cost = position["avg_cost"] if position else 0
            
            # 获取历史净值计算回撤
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
        
        # 6. 执行交易
        action = "HOLD"
        if signal == Signal.BUY:
            # 检查是否已有持仓
            if self.account.get_position(self.symbol):
                logger.info("已有持仓，跳过买入")
            else:
                success = self.executor.execute_signal(self.symbol, signal, latest_price, trade_date)
                action = "BUY" if success else "HOLD"
        
        elif signal == Signal.SELL:
            # 检查是否有持仓
            if not self.account.get_position(self.symbol):
                logger.info("无持仓，跳过卖出")
            else:
                success = self.executor.execute_signal(self.symbol, signal, latest_price, trade_date)
                action = "SELL" if success else "HOLD"
        
        # 6. 保存状态
        price_map = {self.symbol: latest_price}
        self.executor.save_state(price_map, trade_date)
        
        # 7. 打印账户摘要
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

        # 8. 发送通知
        self._send_notification(
            trade_date=trade_date,
            signal=signal.value,
            action=action,
            latest_price=latest_price,
            total_equity=total_equity,
        )

        return True
    
    def _fetch_data(self) -> pd.DataFrame:
        """获取数据"""
        # 尝试主数据源
        provider = get_provider(self.provider_name)
        logger.info(f"📥 使用数据源: {self.provider_name}")
        
        # 获取最近60个交易日数据
        end = datetime.now()
        start = end - timedelta(days=90)  # 多取一些，确保够60个交易日
        
        try:
            data = provider.fetch_ohlcv(
                self.symbol,
                start.strftime("%Y-%m-%d"),
                end.strftime("%Y-%m-%d")
            )
            return data
        except Exception as e:
            logger.warning(f"⚠️ {self.provider_name} 失败: {e}")
            
            # Fallback
            if self.provider_name != "stooq":
                try:
                    provider = get_provider("stooq")
                    logger.info("📥 Fallback 到 Stooq")
                    data = provider.fetch_ohlcv(
                        self.symbol,
                        start.strftime("%Y-%m-%d"),
                        end.strftime("%Y-%m-%d")
                    )
                    return data
                except Exception as e2:
                    logger.warning(f"⚠️ Stooq 也失败: {e2}")
            
            raise RuntimeError(f"数据获取失败: {e}")

    def _send_notification(
        self,
        trade_date: str,
        signal: str,
        action: str,
        latest_price: float,
        total_equity: float,
    ):
        """发送通知"""
        if self.notifier is None:
            return

        # 准备数据
        position = self.account.get_position(self.symbol)
        position_qty = position["quantity"] if position else 0
        avg_cost = position["avg_cost"] if position else 0
        position_value = position_qty * latest_price if position else 0

        # 计算收益
        total_return_pct = (total_equity - self.initial_capital) / self.initial_capital * 100

        data = {
            "trade_date": trade_date,
            "symbol": self.symbol,
            "signal": signal,
            "action": action,
            "cash": self.account.cash,
            "position_qty": position_qty,
            "avg_cost": avg_cost,
            "position_value": position_value,
            "total_equity": total_equity,
            "daily_pnl": 0,  # 简化版
            "total_return_pct": total_return_pct,
            "price": latest_price,
        }

        # 生成消息
        title = f"模拟盘日报 · {trade_date}"
        body = build_daily_report(data, format="markdown")

        # 发送通知
        notifiers = self.notifier if isinstance(self.notifier, list) else [self.notifier]

        for notifier in notifiers:
            try:
                success = notifier.send(title, body)
                if success:
                    logger.info(f"✅ 通知发送成功: {notifier.name}")
                else:
                    logger.warning(f"⚠️ 通知发送失败: {notifier.name}")
            except Exception as e:
                logger.warning(f"⚠️ 通知异常: {e}")

    def load_state(self) -> bool:
        """从数据库恢复状态"""
        if not self.executor:
            return False
        
        self.executor.load_state()
        
        logger.info(f"📂 已加载状态: 现金 {self.account.cash:,.2f}")
        return True
    
    def save_snapshot(self, date: str):
        """保存快照"""
        if not self.executor:
            return
        
        # 获取当前价格
        data = self._fetch_data()
        if data.empty:
            return
        
        latest_price = data["close"].iloc[-1]
        price_map = {self.symbol: latest_price}
        
        self.executor.save_state(price_map, date)
    
    def close(self):
        """关闭连接"""
        if self.db:
            self.db.close()
