"""
交易编排器

每日自动执行完整交易流程
"""
import logging
import subprocess
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum

from .strategy import BaseStrategy, MACrossStrategy
from .strategy.signals import Signal
from .broker import BaseBroker, create_broker
from .data import get_provider
from .storage import Database, OrderRepository, PositionRepository, DailyNavRepository, init_db
from .storage.models import DailyNav
from .policy import load_policy
from .notify import NotifierFactory

logger = logging.getLogger("quant_trader.orchestrator")


class StepStatus(Enum):
    """步骤状态"""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CONTINUE = "continue"  # 失败但继续下一步


@dataclass
class StepResult:
    """步骤执行结果"""
    step_name: str
    status: StepStatus
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Exception] = None


@dataclass
class DailyReport:
    """每日报告"""
    date: str
    steps: List[StepResult] = field(default_factory=list)
    signals: List[Dict] = field(default_factory=list)
    orders: List[Dict] = field(default_factory=list)
    positions: List[Dict] = field(default_factory=list)
    account: Dict[str, float] = field(default_factory=dict)
    total_runtime_seconds: float = 0


class Orchestrator:
    """
    交易编排器
    
    按顺序执行:
    1. 拉取行情数据
    2. 运行策略生成信号
    3. 风控检查
    4. 执行下单
    5. 记录日志
    6. 发送通知
    """
    
    def __init__(
        self,
        broker: BaseBroker,
        strategy: BaseStrategy,
        db: Database,
        symbols: List[str],
        provider_name: str = "stooq",
        notifier: Optional[Any] = None,
    ):
        """
        初始化
        
        Args:
            broker: 券商
            strategy: 策略
            db: 数据库
            symbols: 股票列表
            provider_name: 数据源名称
            notifier: 通知器
        """
        self.broker = broker
        self.strategy = strategy
        self.db = db
        self.symbols = symbols
        self.provider_name = provider_name
        self.notifier = notifier
        
        # 仓库
        self.order_repo = OrderRepository(db)
        self.position_repo = PositionRepository(db)
        self.nav_repo = DailyNavRepository(db)
        
        # 数据源
        self.provider = get_provider(provider_name)
        
        # 策略信号缓存
        self._signals: Dict[str, Signal] = {}
    
    def run_daily(self) -> DailyReport:
        """
        执行每日交易流程
        
        Returns:
            DailyReport: 每日报告
        """
        start_time = datetime.now()
        self._runtime_seconds = 0  # 初始化
        self._report_steps = []  # 用于通知
        report = DailyReport(date=start_time.strftime("%Y-%m-%d"))
        
        logger.info("=" * 50)
        logger.info("🚀 开始每日交易流程")
        logger.info("=" * 50)
        
        # Step 1: 拉取行情数据
        result = self._step_fetch_data()
        report.steps.append(result)
        self._report_steps.append(result)
        
        if result.status == StepStatus.FAILED:
            # Step 1 失败，终止流程
            logger.error("❌ Step 1 失败，终止流程")
            self._send_notification(report)
            report.total_runtime_seconds = (datetime.now() - start_time).total_seconds()
            return report
        
        # Step 2: 运行策略
        result = self._step_generate_signals()
        report.steps.append(result)
        self._report_steps.append(result)
        report.signals = [
            {"symbol": symbol, "signal": signal.value}
            for symbol, signal in self._signals.items()
        ]
        
        # Step 3: 风控检查
        result = self._step_risk_check()
        report.steps.append(result)
        self._report_steps.append(result)
        
        if result.status == StepStatus.FAILED:
            # 风控失败，跳过执行但继续后续步骤
            logger.warning("⚠️ 风控检查失败，跳过执行步骤")
        
        # Step 4: 执行下单 (如果风控通过)
        risk_passed = any(s.status != StepStatus.FAILED for s in report.steps[2:3])
        if risk_passed and self._signals:
            result = self._step_execute_orders()
            report.steps.append(result)
            report.orders = self.order_repo.get_all()
        else:
            report.steps.append(StepResult(
                step_name="Step 4: 执行下单",
                status=StepStatus.SKIPPED,
                message="风控失败或无信号，跳过执行"
            ))
        
        # Step 5: 记录日志
        result = self._step_logging()
        report.steps.append(result)
        self._report_steps.append(result)
        
        # Step 6: 发送通知
        result = self._step_notify()
        report.steps.append(result)
        self._report_steps.append(result)
        
        # 获取最新账户状态
        report.account = self.broker.get_account()
        report.positions = self.broker.get_positions()
        
        self._runtime_seconds = (datetime.now() - start_time).total_seconds()
        report.total_runtime_seconds = self._runtime_seconds
        
        logger.info("=" * 50)
        logger.info(f"✅ 每日交易流程完成，耗时 {self._runtime_seconds:.1f}s")
        logger.info("=" * 50)
        
        return report
    
    def _step_fetch_data(self) -> StepResult:
        """Step 1: 拉取行情数据"""
        logger.info("📊 Step 1: 拉取行情数据")
        
        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now().replace(year=datetime.now().year - 1)).strftime("%Y-%m-%d")
            
            for symbol in self.symbols:
                logger.info(f"  拉取 {symbol}...")
                df = self.provider.fetch_ohlcv(
                    ticker=symbol,
                    start=start_date,
                    end=end_date,
                )
                logger.info(f"    获取 {len(df)} 条数据")
            
            return StepResult(
                step_name="Step 1: 拉取行情数据",
                status=StepStatus.SUCCESS,
                message=f"成功拉取 {len(self.symbols)} 只股票数据",
            )
            
        except Exception as e:
            logger.error(f"  ❌ 拉取失败: {e}")
            return StepResult(
                step_name="Step 1: 拉取行情数据",
                status=StepStatus.FAILED,
                message=str(e),
                error=e,
            )
    
    def _step_generate_signals(self) -> StepResult:
        """Step 2: 运行策略生成信号"""
        logger.info("📈 Step 2: 运行策略生成信号")
        
        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now().replace(month=datetime.now().month - 1)).strftime("%Y-%m-%d")
            
            for symbol in self.symbols:
                logger.info(f"  分析 {symbol}...")
                
                # 拉取数据
                df = self.provider.fetch_ohlcv(
                    ticker=symbol,
                    start=start_date,
                    end=end_date,
                )
                
                if df.empty:
                    logger.warning(f"    无数据，跳过")
                    continue
                
                # 生成信号
                signal = self.strategy.generate_signal(df)
                self._signals[symbol] = signal
                
                emoji = "🟢" if signal == Signal.BUY else "🔴" if signal == Signal.SELL else "⚪"
                logger.info(f"    {emoji} {symbol}: {signal.value}")
            
            return StepResult(
                step_name="Step 2: 运行策略生成信号",
                status=StepStatus.SUCCESS,
                message=f"生成 {len(self._signals)} 个信号",
            )
            
        except Exception as e:
            logger.error(f"  ❌ 策略执行失败: {e}")
            return StepResult(
                step_name="Step 2: 运行策略生成信号",
                status=StepStatus.FAILED,
                message=str(e),
                error=e,
            )
    
    def _step_risk_check(self) -> StepResult:
        """Step 3: 风控检查"""
        logger.info("🛡️ Step 3: 风控检查")
        
        try:
            policy = load_policy()
            
            # 检查账户资金
            account = self.broker.get_account()
            cash = account.get("cash", 0)
            
            logger.info(f"  账户现金: HKD {cash:,.2f}")
            
            # 检查持仓集中度
            positions = self.broker.get_positions()
            total_value = sum(p.get("market_value", 0) for p in positions)
            
            logger.info(f"  持仓市值: HKD {total_value:,.2f}")
            
            # 检查是否有足够的资金
            if self._signals:
                # 简单检查：有买入信号时现金是否足够
                buy_signals = [s for s in self._signals.values() if s == Signal.BUY]
                if buy_signals and cash < 10000:
                    logger.warning(f"  ⚠️ 现金不足")
                    return StepResult(
                        step_name="Step 3: 风控检查",
                        status=StepStatus.FAILED,
                        message="现金不足",
                    )
            
            logger.info("  ✅ 风控检查通过")
            return StepResult(
                step_name="Step 3: 风控检查",
                status=StepStatus.SUCCESS,
                message="风控检查通过",
            )
            
        except Exception as e:
            logger.error(f"  ❌ 风控检查失败: {e}")
            return StepResult(
                step_name="Step 3: 风控检查",
                status=StepStatus.FAILED,
                message=str(e),
                error=e,
            )
    
    def _step_execute_orders(self) -> StepResult:
        """Step 4: 执行下单"""
        logger.info("📝 Step 4: 执行下单")
        
        try:
            executed = 0
            
            for symbol, signal in self._signals.items():
                if signal == Signal.HOLD:
                    logger.info(f"  ⏭️ {symbol}: HOLD，跳过")
                    continue
                
                # 获取当前价格（使用最新价）
                try:
                    end_date = datetime.now().strftime("%Y-%m-%d")
                    df = self.provider.fetch_ohlcv(
                        ticker=symbol,
                        start_date=end_date,
                        end=end_date,
                    )
                    if df.empty:
                        continue
                    price = float(df.iloc[-1]["close"])
                except Exception as e:
                    logger.warning(f"  ⚠️ 获取价格失败: {e}")
                    continue
                
                # 计算数量（简单按固定金额）
                qty = 100  # 每次买 100 股
                side = "BUY" if signal == Signal.BUY else "SELL"
                
                logger.info(f"  📌 {symbol}: {side} {qty} @ {price}")
                
                try:
                    order_id = self.broker.place_order(
                        ticker=symbol,
                        side=side,
                        qty=qty,
                        price=price,
                    )
                    
                    # 记录订单
                    self.order_repo.create(
                        ticker=symbol,
                        side=side,
                        qty=qty,
                        price=price,
                        order_id=order_id,
                        status="SUBMITTED",
                    )
                    
                    executed += 1
                    logger.info(f"    ✅ 订单已提交: {order_id}")
                    
                except PermissionError as e:
                    logger.info(f"    ⏭️ 模式限制跳过: {e}")
                except Exception as e:
                    logger.error(f"    ❌ 下单失败: {e}")
            
            return StepResult(
                step_name="Step 4: 执行下单",
                status=StepStatus.SUCCESS,
                message=f"执行 {executed} 个订单",
            )
            
        except Exception as e:
            logger.error(f"  ❌ 执行失败: {e}")
            return StepResult(
                step_name="Step 4: 执行下单",
                status=StepStatus.FAILED,
                message=str(e),
                error=e,
            )
    
    def _step_logging(self) -> StepResult:
        """Step 5: 记录交易日志"""
        logger.info("💾 Step 5: 记录交易日志")
        
        try:
            # 记录每日净值
            account = self.broker.get_account()
            positions = self.broker.get_positions()
            
            positions_value = sum(p.get("market_value", 0) for p in positions)
            total_assets = account.get("cash", 0) + positions_value
            
            today = datetime.now().strftime("%Y-%m-%d")
            
            nav = DailyNav(
                trade_date=today,
                total_equity=total_assets,
                cash=account.get("cash", 0),
                position_value=positions_value,
                created_at=datetime.now().isoformat(),
            )
            self.nav_repo.create(nav)
            
            logger.info(f"  ✅ 记录净值: HKD {total_assets:,.2f}")
            
            return StepResult(
                step_name="Step 5: 记录交易日志",
                status=StepStatus.SUCCESS,
                message=f"记录净值 HKD {total_assets:,.2f}",
            )
            
        except Exception as e:
            logger.error(f"  ❌ 记录失败: {e}")
            return StepResult(
                step_name="Step 5: 记录交易日志",
                status=StepStatus.FAILED,
                message=str(e),
                error=e,
            )
    
    def _step_notify(self) -> StepResult:
        """Step 6: 发送通知"""
        logger.info("📧 Step 6: 发送通知")
        
        # 加载通知配置
        policy = load_policy()
        config = getattr(policy, 'notifications', None)
        
        if not config:
            logger.info("  ⏭️ 未配置通知器，跳过")
            return StepResult(
                step_name="Step 6: 发送通知",
                status=StepStatus.SKIPPED,
                message="未配置通知器",
            )
        
        # 格式化消息（直接在 Step 6 里构造）
        account = self.broker.get_account()
        cash = account.get('cash', 0)
        risk_status = "正常"
        
        signal_texts = []
        for symbol, signal in self._signals.items():
            signal_texts.append(f"{symbol} → {signal.name} ({str(signal.value)})")
        
        message = (
            f"📊 量化交易日报 | {datetime.now().strftime('%Y-%m-%d')}\n"
            f"\n"
            f"📈 信号：{', '.join(signal_texts) if signal_texts else '无'}\n"
            f"💰 账户净值：HKD {cash:,.2f}\n"
            f"🛡️ 风控状态：{risk_status}\n"
            f"⏱️ 运行耗时：{self._runtime_seconds:.1f}s\n"
            f"🔧 模式：{self.broker.mode}"
        )
        
        # 检查是否有告警
        has_alert = any(s.status == StepStatus.FAILED for s in self._report_steps)
        if has_alert:
            message = f"⚠️ 告警\n\n{message}"
        
        sent = False
        errors = []
        
        # Telegram 通知
        telegram_config = getattr(config, 'telegram', None)
        if telegram_config and getattr(telegram_config, 'enabled', False):
            chat_id = getattr(telegram_config, 'chat_id', None)
            if chat_id:
                try:
                    result = subprocess.run(
                        ["openclaw", "message", "send", "--channel", "telegram", "--target", chat_id, "--message", message],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        logger.warning(f"  ⚠️ Telegram 通知失败: {result.stderr}")
                        errors.append(f"Telegram: {result.stderr}")
                    else:
                        logger.info("  ✅ Telegram 通知发送成功")
                        sent = True
                except Exception as e:
                    logger.warning(f"  ⚠️ Telegram 通知异常: {e}")
                    errors.append(f"Telegram: {e}")
            else:
                logger.warning("  ⚠️ Telegram chat_id 未配置")
        
        # Gmail 通知 (备用)
        email_config = getattr(config, 'email', None)
        if email_config and getattr(email_config, 'enabled', False):
            # Gmail 发送逻辑（如果配置了的话）
            logger.info("  📧 Gmail 通知（暂未实现）")
        
        if sent:
            return StepResult(
                step_name="Step 6: 发送通知",
                status=StepStatus.SUCCESS,
                message="通知已发送",
            )
        elif errors:
            return StepResult(
                step_name="Step 6: 发送通知",
                status=StepStatus.FAILED,
                message="; ".join(errors),
            )
        else:
            return StepResult(
                step_name="Step 6: 发送通知",
                status=StepStatus.SKIPPED,
                message="通知未启用",
            )
    
    def _format_notification(self) -> str:
        """格式化通知内容"""
        # 获取账户信息
        account = self.broker.get_account()
        cash = account.get('cash', 0)
        
        # 获取风控状态
        risk_passed = all(s.status != StepStatus.FAILED for s in self.steps if "风控" in s.step_name)
        risk_status = "正常" if risk_passed else "异常"
        
        # 获取信号
        signal_texts = []
        for symbol, signal in self._signals.items():
            signal_texts.append(f"{symbol} → {signal.name} ({str(signal.value)})")
        
        # 格式化
        lines = [
            f"📊 量化交易日报 | {datetime.now().strftime('%Y-%m-%d')}",
            "",
            f"📈 信号：{', '.join(signal_texts) if signal_texts else '无'}",
            f"💰 账户净值：HKD {cash:,.2f}",
            f"🛡️ 风控状态：{risk_status}",
            f"⏱️ 运行耗时：{self._runtime_seconds:.1f}s",
            f"🔧 模式：{self.broker.mode}",
        ]
        
        return "\n".join(lines)
    
    def _send_notification(self, report: DailyReport):
        """发送告警（失败时）"""
        if not self.notifier:
            return
        
        try:
            content = f"""
❌ 每日交易流程失败

日期: {report.date}
失败步骤: {report.steps[0].step_name if report.steps else 'N/A'}
错误信息: {report.steps[0].message if report.steps else 'N/A'}
"""
            self.notifier.send(title="交易异常告警", content=content)
        except Exception as e:
            logger.error(f"告警发送失败: {e}")


def create_orchestrator(
    broker_config: Dict,
    symbols: List[str],
    provider_name: str = "stooq",
) -> Orchestrator:
    """
    创建编排器
    
    Args:
        broker_config: 券商配置
        symbols: 股票列表
        provider_name: 数据源名称
        
    Returns:
        Orchestrator 实例
    """
    # 加载配置
    policy = load_policy()
    
    # 创建券商
    broker = create_broker(broker_config)
    
    # 连接券商
    if not broker.connect():
        logger.warning("⚠️ 券商连接失败，将以只读模式运行")
    
    # 创建策略
    strategy = MACrossStrategy(short_window=5, long_window=20)
    
    # 创建数据库
    db = Database("data/trading.db")
    init_db("data/trading.db")
    
    # 创建通知器（可选）
    notifier = None
    try:
        notifier = NotifierFactory.create({"channels": []})
    except Exception as e:
        logger.warning(f"通知器创建失败: {e}")
    
    return Orchestrator(
        broker=broker,
        strategy=strategy,
        db=db,
        symbols=symbols,
        provider_name=provider_name,
        notifier=notifier,
    )
