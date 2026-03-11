"""
Agent 交易接口层

为 Agent 提供统一的交易能力
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from .broker.paper_broker import PaperBroker
from .data.source_manager import DataSourceManager
from .order_guard import OrderGuard
from .reconciler import Reconciler
from .notify import NotifierFactory
from .config import get_settings

logger = logging.getLogger("quant_trader.agent_interface")


class RiskConfig:
    """
    风控配置
    """
    
    def __init__(self):
        settings = get_settings()
        self.max_position_ratio = 0.10
        self.max_daily_loss = -0.015
        self.stop_loss = -0.02
        self.max_daily_orders = 3
        self.cooldown_seconds = 300

        tz_str = settings.timezone
        self.timezone = self._parse_timezone(tz_str)
    
    def _parse_timezone(self, tz_str: str):
        """解析时区字符串"""
        tz_map = {
            "Asia/Hong_Kong": timezone(timedelta(hours=8)),
            "Asia/Shanghai": timezone(timedelta(hours=8)),
            "America/New_York": timezone(timedelta(hours=-5)),
            "America/Los_Angeles": timezone(timedelta(hours=-8)),
            "UTC": timezone.utc,
        }
        return tz_map.get(tz_str, timezone(timedelta(hours=8)))
    
    def now(self) -> datetime:
        """获取当前时间（配置时区）"""
        return datetime.now(self.timezone)


class AgentTrader:
    """
    Agent 交易接口
    
    提供 Agent 需要的基本交易能力:
    - 获取持仓
    - 获取市场数据
    - 执行交易
    - 发送通知
    """
    
    def __init__(
        self,
        initial_capital: float = 1_000_000,
        data_dir: str = None,
    ):
        """
        Args:
            initial_capital: 初始资金 (模拟盘)
            data_dir: 数据目录
        """
        # 券商 (模拟盘)
        self.broker = PaperBroker(initial_capital=initial_capital)
        self.broker.connect()
        
        # 数据源
        self.data_manager = DataSourceManager()
        
        # 订单防护
        self.order_guard = OrderGuard(data_dir=data_dir)
        
        # 对账器
        self.reconciler = Reconciler(broker=self.broker)
        
        # 通知器 (初始化一次)
        self._notifier = None
        
        # 风控配置
        self.risk_config = RiskConfig()
        
        # 初始权益 & 每日开始权益
        self._initial_capital = initial_capital
        self._day_start_assets = initial_capital
        
        logger.info(f"✅ AgentTrader initialized: capital={initial_capital}")
    
    def reset_daily(self):
        """重置每日状态 (每日开盘前调用)"""
        self._day_start_assets = self.get_account()["total_assets"]
        logger.info(f"📅 每日重置: day_start_assets={self._day_start_assets}")
    
    # ==================== 通知器 ====================
    
    def _get_notifier(self):
        """获取通知器实例"""
        if self._notifier is None:
            self._notifier = NotifierFactory.create("telegram", {})
        return self._notifier
    
    # ==================== 持仓相关 ====================
    
    def get_positions(self) -> list[dict]:
        """获取当前持仓"""
        return self.broker.get_positions()
    
    def get_account(self) -> dict:
        """获取账户信息"""
        return self.broker.get_account()
    
    # ==================== 市场数据 ====================
    
    def get_price(self, ticker: str) -> Optional[float]:
        """获取最新价格"""
        return self.data_manager.fetch_latest_price(ticker)
    
    def get_ohlcv(
        self,
        ticker: str,
        days: int = 30,
    ) -> Optional[dict]:
        """
        获取 K 线数据
        
        Args:
            ticker: 股票代码
            days: 天数
            
        Returns:
            dict with 'dates', 'open', 'high', 'low', 'close', 'volume'
        """
        end = self.risk_config.now()
        start = (end - timedelta(days=days * 2)).strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")
        
        df = self.data_manager.fetch_ohlcv(ticker, start, end_str)
        
        if df is None or df.empty:
            return None
        
        # 只返回最近 days 天
        df = df.tail(days)
        
        return {
            "dates": df.index.strftime("%Y-%m-%d").tolist(),
            "open": df["open"].tolist(),
            "high": df["high"].tolist(),
            "low": df["low"].tolist(),
            "close": df["close"].tolist(),
            "volume": df["volume"].tolist(),
        }
    
    # ==================== 风控检查 ====================
    
    def check_position_limit(self, order_value: float) -> tuple[bool, str]:
        """
        检查仓位是否超限
        
        Returns:
            (allowed, reason)
        """
        account = self.get_account()
        total_assets = account["total_assets"]
        ratio = order_value / total_assets
        
        if ratio > self.risk_config.max_position_ratio:
            return False, f"单笔仓位超限: {ratio:.1%} > {self.risk_config.max_position_ratio:.0%}"
        
        return True, "OK"
    
    def check_daily_loss_limit(self) -> tuple[bool, str]:
        """
        检查单日亏损是否超限 (基于 _day_start_assets)
        
        Returns:
            (allowed, reason)
        """
        account = self.get_account()
        current_assets = account["total_assets"]
        
        # 基于当日开盘计算亏损
        loss_ratio = (current_assets - self._day_start_assets) / self._day_start_assets
        
        if loss_ratio < self.risk_config.max_daily_loss:
            return False, f"单日亏损超限: {loss_ratio:.1%} < {self.risk_config.max_daily_loss:.1%}"
        
        return True, "OK"
    
    # ==================== 交易执行 ====================
    
    def can_buy(self, ticker: str) -> tuple[bool, str]:
        """
        检查是否可以买入
        
        Returns:
            (allowed, reason)
        """
        # 检查单日亏损
        allowed, reason = self.check_daily_loss_limit()
        if not allowed:
            return False, reason
        
        # 检查订单防护
        report = self.order_guard.can_order(ticker, "BUY")
        return report.allowed, report.reason
    
    def can_sell(self, ticker: str) -> tuple[bool, str]:
        """
        检查是否可以卖出
        
        Returns:
            (allowed, reason)
        """
        # 检查单日亏损
        allowed, reason = self.check_daily_loss_limit()
        if not allowed:
            return False, reason
        
        # 检查订单防护
        report = self.order_guard.can_order(ticker, "SELL")
        return report.allowed, report.reason
    
    def buy(
        self,
        ticker: str,
        qty: int,
        price: Optional[float] = None,
    ) -> dict:
        """
        买入
        
        Args:
            ticker: 股票代码
            qty: 数量
            price: 价格 (None = 市价)
            
        Returns:
            dict with 'success', 'order_id', 'message'
        """
        # 检查是否可以买入
        allowed, reason = self.can_buy(ticker)
        if not allowed:
            return {"success": False, "order_id": "", "message": reason}
        
        # 获取价格
        if price is None:
            price = self.get_price(ticker)
            if price is None:
                return {"success": False, "order_id": "", "message": "无法获取价格"}
        
        # 检查仓位
        account = self.get_account()
        order_value = qty * price
        
        allowed, reason = self.check_position_limit(order_value)
        if not allowed:
            return {"success": False, "order_id": "", "message": reason}
        
        # 执行买入
        order_id = self.broker.place_order(ticker, "BUY", qty, price)
        
        # 记录订单
        self.order_guard.record_order(ticker, "BUY", qty, price, order_id)
        
        logger.info(f"🟢 买入 {ticker} x {qty} @ {price}")
        
        return {
            "success": True,
            "order_id": order_id,
            "message": f"买入成功: {ticker} x {qty} @ {price}"
        }
    
    def sell(
        self,
        ticker: str,
        qty: int,
        price: Optional[float] = None,
    ) -> dict:
        """
        卖出
        
        Args:
            ticker: 股票代码
            qty: 数量
            price: 价格 (None = 市价)
            
        Returns:
            dict with 'success', 'order_id', 'message'
        """
        # 检查是否可以卖出
        allowed, reason = self.can_sell(ticker)
        if not allowed:
            return {"success": False, "order_id": "", "message": reason}
        
        # 获取价格
        if price is None:
            price = self.get_price(ticker)
            if price is None:
                return {"success": False, "order_id": "", "message": "无法获取价格"}
        
        # 执行卖出
        order_id = self.broker.place_order(ticker, "SELL", qty, price)
        
        # 记录订单
        self.order_guard.record_order(ticker, "SELL", qty, price, order_id)
        
        logger.info(f"🔴 卖出 {ticker} x {qty} @ {price}")
        
        return {
            "success": True,
            "order_id": order_id,
            "message": f"卖出成功: {ticker} x {qty} @ {price}"
        }
    
    # ==================== 通知 ====================
    
    def send_report(self, message: str, chat_id: str = None) -> bool:
        """
        发送报告 (Telegram)
        
        Args:
            message: 消息内容
            chat_id: Telegram chat_id
            
        Returns:
            bool: 是否发送成功
        """
        try:
            notifier = self._get_notifier()
            if chat_id:
                notifier.chat_id = chat_id
            
            notifier.send(message)
            logger.info(f"📢 报告已发送: {message[:50]}...")
            return True
        except Exception as e:
            logger.error(f"❌ 发送报告失败: {e}")
            return False
    
    # ==================== 状态 ====================
    
    def get_status(self) -> dict:
        """获取完整状态"""
        account = self.get_account()
        positions = self.get_positions()
        order_status = self.order_guard.get_status()
        
        return {
            "account": account,
            "positions": positions,
            "order_guard": order_status,
            "data_status": self.data_manager.get_provider_status(),
        }
    
    def get_reconcile_report(self) -> Optional[dict]:
        """
        获取对账报告
        
        Returns:
            dict or None
        """
        try:
            report = self.reconciler.reconcile()
            return {
                "is_balanced": report.is_balanced,
                "actions": report.actions,
                "errors": report.errors,
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_daily_report(self) -> str:
        """生成每日报告"""
        account = self.get_account()
        positions = self.get_positions()
        order_status = self.order_guard.get_status()
        
        # 基于当日开盘计算盈亏
        pnl_value = account['total_assets'] - self._day_start_assets
        pnl_ratio = pnl_value / self._day_start_assets
        
        now_str = self.risk_config.now().strftime("%Y-%m-%d %H:%M:%S %Z")
        
        lines = [
            "📊 每日交易报告",
            f"📅 {now_str}",
            "",
            "💰 账户:",
            f"  开盘资产: ${self._day_start_assets:,.0f}",
            f"  现金: ${account['cash']:,.0f}",
            f"  持仓: ${account['positions_value']:,.0f}",
            f"  总资产: ${account['total_assets']:,.0f}",
            f"  今日盈亏: ${pnl_value:+,.0f} ({pnl_ratio:+.1%})",
            "",
            "📈 持仓:",
        ]
        
        if positions:
            for p in positions:
                lines.append(f"  {p['symbol']}: {p['qty']}股 @ ${p['avg_cost']:.2f}")
        else:
            lines.append("  (无持仓)")
        
        lines.append("")
        lines.append("🛡️ 订单状态:")
        lines.append(f"  今日交易: {order_status['today_orders']}/{order_status['max_daily_orders']}")
        
        return "\n".join(lines)


# 全局实例
_trader: Optional[AgentTrader] = None


def get_agent_trader(
    initial_capital: float = 1_000_000,
    data_dir: str = None,
) -> AgentTrader:
    """获取全局 AgentTrader 实例"""
    global _trader
    if _trader is None:
        _trader = AgentTrader(
            initial_capital=initial_capital,
            data_dir=data_dir,
        )
    return _trader


def reset_trader():
    """重置全局实例 (用于测试)"""
    global _trader
    _trader = None
